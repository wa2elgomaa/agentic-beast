const https = require("https");
const fs = require("fs");
const path = require("path");

// --- Config ---
const BASE_URL =
    "https://thenationalnews.tansa.com/tansaadmin/api/entry/getGroupedEntries";
const PARAMS = {
    dictionaryIds: "1000143",
    wordType: "",
    isReference: "0",
    isWarning: "0",
    status: "",
    startWith: "",
    searchWord: "",
    limit: 100,
};
const OUTPUT_FILE = path.join(__dirname, "entries.csv");

// CSV columns (keys from each result object)
const CSV_COLUMNS = [
    "dictionaryWordId",
    "dictionaryId",
    "correct",
    "wordType",
    "isWarning",
    "isReference",
    "status",
    "frequency",
    "relevance",
    "warningType",
    "listId",
    "name",
    "creatorUserId",
    "clientComment",
    "search",
];

// --- Helpers ---

function buildUrl(page) {
    const params = new URLSearchParams({ ...PARAMS, page });
    return `${BASE_URL}?${params.toString()}`;
}

const AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJfaWQiOjMwOTI5LCJjdXN0b21lcklkIjo1NSwibG9nSWQiOjExNTY5LCJpYXQiOjE3NzMwNDc3ODUsImV4cCI6MTc3MzEzNDE4NX0.bkLItRfC1WCDdzuFazGJNzcZLHyHAkJxtz471xEPokg";

function fetchPage(page) {
    return new Promise((resolve, reject) => {
        const url = buildUrl(page);
        const options = {
            headers: {
                Authorization: `Bearer ${AUTH_TOKEN}`,
            },
        };
        https
            .get(url, options, (res) => {
                let raw = "";
                res.on("data", (chunk) => (raw += chunk));
                res.on("end", () => {
                    try {
                        resolve(JSON.parse(raw));
                    } catch (e) {
                        reject(new Error(`JSON parse error on page ${page}: ${e.message}`));
                    }
                });
            })
            .on("error", reject);
    });
}

function escapeCsv(value) {
    if (value === null || value === undefined) return "";
    const str = String(value)
        .replace(/<[^>]*>/g, "") // strip HTML tags
        .replace(/\r?\n/g, " "); // flatten newlines
    // Wrap in quotes if contains comma, quote, or newline
    if (str.includes(",") || str.includes('"') || str.includes("\n")) {
        return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
}

function rowToCsv(entry) {
    return CSV_COLUMNS.map((col) => escapeCsv(entry[col])).join(",");
}

// --- Main ---

async function main() {
    // Write CSV header (overwrite file at start)
    fs.writeFileSync(OUTPUT_FILE, CSV_COLUMNS.join(",") + "\n", "utf8");

    let page = 1;
    let totalFetched = 0;
    let totalCount = null;
    let totalPages = null;

    console.log("Starting paginated fetch...\n");

    while (true) {
        process.stdout.write(`Fetching page ${page}...`);

        let json;
        try {
            json = await fetchPage(page);
        } catch (err) {
            console.error(`\nFailed on page ${page}: ${err.message}`);
            break;
        }

        const result = json?.data?.result;
        const meta = json?.data?.meta;

        if (!Array.isArray(result) || result.length === 0) {
            console.log(" No results. Done.");
            break;
        }

        if (totalCount === null && meta?.totalCount) {
            totalCount = meta.totalCount;
            totalPages = meta.pageCount ?? null;
            console.log(`  Total records: ${totalCount}, total pages: ${totalPages ?? "unknown"}`);
        }

        // Append rows to CSV
        const rows = result.map(rowToCsv).join("\n") + "\n";
        fs.appendFileSync(OUTPUT_FILE, rows, "utf8");

        totalFetched += result.length;
        const pct = totalCount ? ` (${((totalFetched / totalCount) * 100).toFixed(1)}%)` : "";
        console.log(` got ${result.length} rows. Total so far: ${totalFetched}${totalCount ? ` / ${totalCount}` : ""}${pct}`);

        // Stop if we have collected every record
        if (totalCount !== null && totalFetched >= totalCount) {
            console.log("\nAll records fetched.");
            break;
        }

        // Stop if we have exceeded the known page count (safety cap)
        if (totalPages !== null && page >= totalPages) {
            console.log("\nReached last page.");
            break;
        }

        page++;

        // Small delay to be polite to the server
        await new Promise((r) => setTimeout(r, 150));
    }

    console.log(`\nDone! ${totalFetched} rows written to: ${OUTPUT_FILE}`);
}

main().catch((err) => {
    console.error("Fatal error:", err);
    process.exit(1);
});