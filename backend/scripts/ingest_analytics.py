#!/usr/bin/env python3
"""
ingest_analytics.py (updated for multi-file Excel ingestion)

Supports:
- reading all Excel files matching a pattern in a directory (supports incremental ingest)
- canonicalizing combined dataframe
- creating materialized views
- embedding & upserting row summaries to Chroma
- updating metadata.json (includes list of source files and mtimes)

New CLI options:
  --excel-dir  <dir>      Directory with many .xlsx/.xls files
  --pattern    <glob>     File glob pattern to match (default: *.xlsx)
  --incremental <true|false>  If true, only new/changed files are processed (tracked in processed/processed_files.json)

Example:
  python scripts/ingest_analytics.py --mode full --excel-dir data/excels --pattern "*.xlsx" --out data/processed --materialized data/materialized --persist data/vector_db --model all-MiniLM-L6-v2 --metadata data/metadata.json
"""
import argparse
import json
import logging
import os
from pathlib import Path
import time

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingest_analytics_multi")

PROCESSED_FILES_TRACKER = "processed_files.json"

def read_excels(excel_dir: str, pattern: str = "*.xlsx", out_dir: str = None, incremental: bool = True):
    """
    Read all Excel files in excel_dir matching pattern, concatenate them into a single DataFrame.
    If incremental is True, only process files that are new or whose mtime changed since last run.
    Adds columns: __source_file, __source_mtime
    Stores processed_files.json in out_dir to track processed files and their mtimes.
    """
    excel_dir = Path(excel_dir)
    if not excel_dir.exists():
        raise FileNotFoundError(f"Excel directory not found: {excel_dir}")

    files = sorted(list(excel_dir.glob(pattern)))
    logger.info("Found %d files matching %s in %s", len(files), pattern, excel_dir)

    out_dir = Path(out_dir) if out_dir else excel_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    tracker_path = out_dir / PROCESSED_FILES_TRACKER

    processed_record = {}
    if tracker_path.exists():
        try:
            processed_record = json.loads(tracker_path.read_text())
        except Exception:
            processed_record = {}

    dfs = []
    new_or_changed = []

    for f in files:
        try:
            mtime = int(f.stat().st_mtime)
        except Exception:
            mtime = int(time.time())
        key = str(f.resolve())
        prev_mtime = processed_record.get(key)
        if incremental and prev_mtime and int(prev_mtime) == mtime:
            logger.debug("Skipping unchanged file: %s", f.name)
            continue
        logger.info("Reading file: %s (mtime=%s)", f.name, mtime)
        try:
            df = pd.read_excel(f)
        except Exception as e:
            logger.warning("Failed to read %s: %s", f.name, e)
            continue
        # add source tracking columns
        df["__source_file"] = f.name
        df["__source_mtime"] = mtime
        dfs.append(df)
        processed_record[key] = mtime
        new_or_changed.append(f.name)

    if not dfs:
        logger.info("No new or changed files to process.")
        return None, []

    combined = pd.concat(dfs, ignore_index=True, sort=False)
    # save raw combined parquet
    raw_path = out_dir / "raw.parquet"
    combined.to_parquet(raw_path, index=False)
    logger.info("Saved combined raw.parquet: %s (rows=%d cols=%d)", raw_path, len(combined), len(combined.columns))

    # update tracker
    tracker_path.write_text(json.dumps(processed_record, indent=2))
    logger.info("Updated processed files tracker at %s", tracker_path)
    return raw_path, new_or_changed

def canonicalize(in_dir: str, out_dir: str):
    in_dir = Path(in_dir)
    out_dir = Path(out_dir)
    raw_path = in_dir / "raw.parquet"
    if not raw_path.exists():
        raise FileNotFoundError(f"{raw_path} does not exist. Run read mode first.")
    df = pd.read_parquet(raw_path)
    # Lowercase and snake_case column names
    def normalize_col(c: str) -> str:
        return c.strip().lower().replace(" ", "_").replace("-", "_")
    df.columns = [normalize_col(c) for c in df.columns]
    # Try to parse date-like columns
    for col in df.columns:
        if "date" in col or col.endswith("_at"):
            try:
                df[col] = pd.to_datetime(df[col], errors="coerce")
            except Exception:
                pass
    # Create month/year columns if date exists
    date_cols = [c for c in df.columns if "date" in c or c.endswith("_at")]
    if date_cols:
        main_date_col = date_cols[0]
        df["__ingest_date_col"] = main_date_col
        df["month"] = df[main_date_col].dt.to_period("M").astype(str)
        df["year"] = df[main_date_col].dt.year
    out_dir.mkdir(parents=True, exist_ok=True)
    processed_path = out_dir / "processed.parquet"
    df.to_parquet(processed_path, index=False)
    logger.info("Saved processed parquet: %s (rows=%d cols=%d)", processed_path, len(df), len(df.columns))
    return processed_path

def materialize(in_dir: str, out_dir: str):
    in_dir = Path(in_dir)
    out_dir = Path(out_dir)
    processed_path = in_dir / "processed.parquet"
    if not processed_path.exists():
        raise FileNotFoundError(f"{processed_path} not found. Run canonicalize first.")
    df = pd.read_parquet(processed_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Build monthly totals for numeric columns
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    if "month" in df.columns and numeric_cols:
        monthly = df.groupby("month")[numeric_cols].sum().reset_index()
        monthly_path = out_dir / "monthly_totals.parquet"
        monthly.to_parquet(monthly_path, index=False)
        logger.info("Saved monthly totals: %s", monthly_path)
    # daily totals if date column exists
    date_cols = [c for c in df.columns if "date" in c or c.endswith("_at")]
    if date_cols and numeric_cols:
        date_col = date_cols[0]
        df["_date_only"] = df[date_col].dt.date
        daily = df.groupby("_date_only")[numeric_cols].sum().reset_index()
        daily_path = out_dir / "daily_totals.parquet"
        daily.to_parquet(daily_path, index=False)
        logger.info("Saved daily totals: %s", daily_path)
    # Save sample rows
    sample_path = out_dir / "sample_rows.parquet"
    df.head(200).to_parquet(sample_path, index=False)
    logger.info("Saved sample rows: %s", sample_path)
    return out_dir

def create_row_summaries(df: pd.DataFrame, text_cols: list = None):
    # Concatenate best textual columns into a compact summary
    if text_cols is None:
        text_cols = [c for c in df.columns if df[c].dtype == object][:3]
    if not text_cols:
        # fallback: use first 3 columns
        text_cols = df.columns.tolist()[:3]
    texts = df[text_cols].fillna("").astype(str).agg(" | ".join, axis=1).tolist()
    return texts, text_cols

def embed_upsert(in_dir: str, vector_db: str, persist: str, model_name: str, batch_size: int = 64):
    in_dir = Path(in_dir)
    processed_path = in_dir / "processed.parquet"
    if not processed_path.exists():
        raise FileNotFoundError(f"{processed_path} not found. Run canonicalize first.")
    df = pd.read_parquet(processed_path)
    # Create row summaries
    texts, text_cols = create_row_summaries(df)
    logger.info("Embedding %d rows using model %s; text cols: %s", len(texts), model_name, text_cols)
    embedder = SentenceTransformer(model_name)
    embeddings = embedder.encode(texts, batch_size=batch_size, show_progress_bar=True)
    embeddings = np.array(embeddings)
    # Upsert into Chroma (local)
    persist = Path(persist)
    persist.mkdir(parents=True, exist_ok=True)
    logger.info("Initializing Chroma client at %s", persist)
    client = chromadb.Client(Settings(persist_directory=str(persist)))
    collection = client.get_or_create_collection(name="analytics_rows")
    ids = [str(i) for i in df.index.tolist()]
    metadatas = df[[*text_cols]].fillna("").astype(str).to_dict(orient="records")
    documents = texts
    try:
        collection.upsert(ids=ids, embeddings=embeddings.tolist(), metadatas=metadatas, documents=documents)
    except Exception:
        collection.add(ids=ids, embeddings=embeddings.tolist(), metadatas=metadatas, documents=documents)
    client.persist()
    logger.info("Upserted %d embeddings to Chroma at %s", len(ids), persist)
    emb_meta = {
        "model": model_name,
        "rows": len(ids),
        "text_columns": text_cols,
        "timestamp": int(time.time())
    }
    (persist / "embeddings_meta.json").write_text(json.dumps(emb_meta, indent=2))
    return persist

def update_metadata(in_dir: str, out_path: str):
    in_dir = Path(in_dir)
    processed_path = in_dir / "processed.parquet"
    if not processed_path.exists():
        raise FileNotFoundError(f"{processed_path} not found. Run canonicalize first.")
    df = pd.read_parquet(processed_path)
    # include list of discovered source files and processed_files tracker if present
    tracker_path = in_dir / PROCESSED_FILES_TRACKER
    processed_files = {}
    if tracker_path.exists():
        try:
            processed_files = json.loads(tracker_path.read_text())
        except Exception:
            processed_files = {}
    meta = {
        "columns": [
            {"name": c, "dtype": str(df[c].dtype), "sample_values": df[c].dropna().unique()[:5].tolist()}
            for c in df.columns
        ],
        "rows": int(len(df)),
        "source_files": list(processed_files.keys()),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(meta, indent=2))
    logger.info("Wrote metadata to %s", out_path)
    return out_path

def run_full(excel_dir, pattern, out, materialized, vector_db, persist, model, batch, metadata, incremental):
    raw, changed = read_excels(excel_dir, pattern, out_dir=out, incremental=incremental)
    if raw is None:
        logger.info("No new files found (incremental) — exiting full run.")
        return
    canonicalize(out, out)
    materialize(out, materialized)
    embed_upsert(out, vector_db, persist, model, batch)
    update_metadata(out, metadata)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["read","canonicalize","materialize","embed_upsert","update_metadata","full"])
    parser.add_argument("--excel", help="(deprecated) single Excel file path (kept for compatibility)")
    parser.add_argument("--excel-dir", help="Directory containing multiple Excel files")
    parser.add_argument("--pattern", default="*.xlsx", help="Glob pattern to match Excel files")
    parser.add_argument("--out", help="Processed output directory (for read/canonicalize/full)")
    parser.add_argument("--in", dest="in_dir", help="Input processed directory (for canonicalize/materialize/embed_upsert/update_metadata)")
    parser.add_argument("--materialized", help="Materialized views output directory (for full or materialize)")
    parser.add_argument("--vector-db", default="chroma", help="Vector DB type (chroma/faiss...)")
    parser.add_argument("--persist", help="Vector DB persist directory")
    parser.add_argument("--model", default="all-MiniLM-L6-v2", help="Embedding model name")
    parser.add_argument("--batch", type=int, default=64, help="Embedding batch size")
    parser.add_argument("--metadata", help="Metadata output path")
    parser.add_argument("--incremental", type=str, default="true", help="true/false incremental ingest")
    return parser.parse_args()

def main():
    args = parse_args()
    incremental_flag = str(args.incremental).lower() in ("1","true","yes","y")
    try:
        if args.mode == "read":
            if args.excel_dir:
                read_excels(args.excel_dir, pattern=args.pattern, out_dir=args.out, incremental=incremental_flag)
            elif args.excel:
                # backward compatibility: read single excel
                read_excels(Path(args.excel).parent, pattern=Path(args.excel).name, out_dir=args.out, incremental=incremental_flag)
            else:
                raise SystemExit("--excel-dir or --excel required for read")
        elif args.mode == "canonicalize":
            if not args.in_dir or not args.out:
                raise SystemExit("--in and --out are required for canonicalize")
            canonicalize(args.in_dir, args.out)
        elif args.mode == "materialize":
            if not args.in_dir or not args.out:
                raise SystemExit("--in and --out are required for materialize")
            materialize(args.in_dir, args.out)
        elif args.mode == "embed_upsert":
            if not args.in_dir or not args.persist:
                raise SystemExit("--in and --persist are required for embed_upsert")
            embed_upsert(args.in_dir, args.vector_db, args.persist, args.model, args.batch)
        elif args.mode == "update_metadata":
            if not args.in_dir or not args.metadata:
                raise SystemExit("--in and --metadata are required for update_metadata")
            update_metadata(args.in_dir, args.metadata)
        elif args.mode == "full":
            if not all([args.excel_dir, args.out, args.materialized, args.persist, args.metadata]):
                raise SystemExit("--excel-dir --out --materialized --persist --metadata are required for full")
            run_full(args.excel_dir, args.pattern, args.out, args.materialized, args.vector_db, args.persist, args.model, args.batch, args.metadata, incremental_flag)
        else:
            raise SystemExit("Unknown mode")
    except Exception as e:
        logger.exception("Ingestion failed: %s", e)
        raise

if __name__ == "__main__":
    main()