#!/usr/bin/env python3
"""Inspect Excel files and show column structure."""

import pandas as pd
import os
import sys

excel_dir = '/app/data/analytics'
excel_files = sorted([f for f in os.listdir(excel_dir) if f.endswith('.xlsx')])

print("\n" + "="*100)
print("EXCEL FILES COLUMN STRUCTURE ANALYSIS")
print("="*100)

for excel_file in excel_files:
    file_path = os.path.join(excel_dir, excel_file)
    print(f"\n📄 FILE: {excel_file}")
    print("-"*100)
    
    try:
        excel_file_obj = pd.ExcelFile(file_path)
        print(f"Sheets: {excel_file_obj.sheet_names}\n")
        
        for sheet_name in excel_file_obj.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            print(f"  📋 SHEET: '{sheet_name}'")
            print(f"     Rows: {len(df)} | Columns: {len(df.columns)}\n")
            print(f"     COLUMN NAMES:")
            for i, col in enumerate(df.columns, 1):
                print(f"        {i:2d}. {col}")
            
            if len(df) > 0:
                print(f"\n     SAMPLE DATA (First Row):")
                for col in df.columns:
                    val = df[col].iloc[0]
                    if pd.isna(val):
                        val_str = "NULL"
                    else:
                        val_str = str(val)[:60]
                    print(f"        {col}: {val_str}")
            print()
            
    except Exception as e:
        print(f"  ❌ Error: {e}")

print("="*100 + "\n")
