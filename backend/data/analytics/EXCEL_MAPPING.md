# Excel to Documents Table Mapping

**Generated**: March 6, 2026  
**Source Files**: 
- `data/analytics/feb-2026.xlsx` (5,634 rows × 133 columns, 'Content' sheet)
- `data/analytics/nov-2025.xlsx` (1,492 rows × 41 columns, 'Content' sheet)

---

## 📊 Summary

| Source | File | Sheet | Rows | Columns |
|--------|------|-------|------|---------|
| Excel 1 | **feb-2026.xlsx** | Content | 5,634 | 133 |
| Excel 2 | **nov-2025.xlsx** | Content | 1,492 | 41 |
| **Database** | **documents** | - | - | **73** |

---

## 🔄 Column Mapping: PROPOSED

### ✅ **DIRECT MAPPINGS** (Excel Column → Database Column)

These columns appear directly in the Excel files with compatible names/data:

| # | Excel Column | Database Column | Type | Notes |
|---|--------------|-----------------|------|-------|
| 1 | Reported at | reported_at | DATE | Convert from datetime |
| 2 | Profile name | profile_name | TEXT | |
| 3 | Profile URL | profile_url | TEXT | |
| 4 | Profile ID | profile_id | TEXT | |
| 5 | Post detail URL | post_detail_url | TEXT | |
| 6 | Content ID | content_id | TEXT | |
| 7 | Platform | platform | TEXT | facebook, tiktok, etc. |
| 8 | Content type | content_type | TEXT | post, story, etc. |
| 9 | Media type | media_type | TEXT | link, video, photo, etc. |
| 10 | Origin of the content | origin_of_the_content | TEXT | |
| 11 | Title | title | TEXT | |
| 12 | Description | description | TEXT | |
| 13 | Author URL | author_url | TEXT | |
| 14 | Author ID | author_id | TEXT | |
| 15 | Author name | author_name | TEXT | |
| 16 | Content | content | TEXT | Main post/content text |
| 17 | Link URL | link_url | TEXT | |
| 18 | View on platform | view_on_platform | TEXT | |
| 19 | Organic interactions | organic_interactions | INT | |
| 20 | Total interactions | total_interactions | INT | |
| 21 | Total reactions | total_reactions | INT | |
| 22 | Total comments | total_comments | INT | |
| 23 | Total shares | total_shares | INT | |
| 24 | Unpublished | unpublished | BOOLEAN | Cast FLOAT → BOOLEAN |
| 25 | Engagements | engagements | INT | Cast FLOAT → INT |
| 26 | Total reach | total_reach | INT | Cast FLOAT → INT |
| 27 | Paid reach | paid_reach | INT | Cast FLOAT → INT |
| 28 | Organic reach | organic_reach | INT | Cast FLOAT → INT |
| 29 | Total impressions | total_impressions | INT | Cast FLOAT → INT |
| 30 | Paid impressions | paid_impressions | INT | Cast FLOAT → INT |
| 31 | Organic impressions | organic_impressions | INT | Cast FLOAT → INT |
| 32 | Reach engagement rate | reach_engagement_rate | NUMERIC | Already decimal |
| 33 | Total likes | total_likes | INT | Cast FLOAT → INT |
| 34 | Video length (sec) | video_length_sec | INT | Cast FLOAT → INT |
| 35 | Video view count | video_views | INT | Map "Video view count" → "video_views" |
| 36 | Total video view time (sec) | total_video_view_time_sec | INT | Cast FLOAT → INT |
| 37 | Completion rate | completion_rate | NUMERIC | Keep as decimal |
| 38 | Labels | labels | TEXT | Pipe-separated or as-is |
| 39 | Label groups | label_groups | TEXT | Pipe-separated or as-is |

---

### ⚠️ **PARTIAL/ADJUSTED MAPPINGS** (Excel Data → Database Columns)

These require data transformation or selection from multiple Excel columns:

| # | Source | Database Column | Type | Transformation |
|---|--------|-----------------|------|-----------------|
| 1 | **Reported at** or **Created timezone** | published_date | DATE | Use "Reported at" value as date |
| 2 | "Content" + "Title" | text | TEXT | Combine content columns into text field |
| 3 | "Avg. Video Views per Video" | N/A | - | Use video_views instead (more accurate) |
| 4 | "Average time watched (sec)" | N/A | - | Can use total_video_view_time_sec ÷ video_views as estimate |
| 5 | Email-free author fields | user_id | UUID | Keep NULL (no direct mapping) |

---

### ❌ **EXCEL COLUMNS WITHOUT DATABASE MAPPING**

These Excel columns have no direct equivalent in the documents table:

| Excel Column | Reason | Recommendation |
|--------------|--------|-----------------|
| Created timezone | Timezone info, not specific date | Store in doc_metadata as JSON |
| Profile followers | User metrics not in schema | Store in doc_metadata as JSON |
| Mentioned profiles ID | Content reference data | Store in doc_metadata as JSON |
| Collaborators | Content collaboration data | Store in doc_metadata as JSON |
| Grade, Last grade | Content quality metrics | Store in doc_metadata as JSON |
| Sentiment | NLP analysis results | Store in doc_metadata as JSON |
| Positive/Negative/Neutral comments | Sentiment breakdown | Store in doc_metadata as JSON |
| Organic likes, Save rate | Legacy metric names | Use mapped fields instead |
| Deleted, Hidden, Spam | Content moderation flags | Store in doc_metadata as JSON |
| Saves, Promoted post detection | Platform-specific metrics | Store in doc_metadata as JSON |
| Reactions breakdown (like, love, wow, etc.) | Individual reaction types | Store in doc_metadata as JSON |
| Shared, Crosspost, Live, etc. | Platform-specific flags | Store in doc_metadata as JSON |
| Engaged users, Negative feedback | Additional engagement metrics | Store in doc_metadata as JSON |
| Lifetime post stories | Stories metrics | Store in doc_metadata as JSON |
| Post consumers, Post clicks | Click metrics | Store in doc_metadata as JSON |
| Photo views, Link clicks, Other clicks | Specific click types | Store in doc_metadata as JSON |
| Media views, Video play | Media metrics | Store in doc_metadata as JSON |
| Insights reactions breakdown | YouTube/platform insights | Store in doc_metadata as JSON |
| Views breakdown (auto-played, organic, paid, unique) | Video view breakdown | Store in doc_metadata as JSON |
| 10-second & 30-second views (all variations) | Video engagement milestones | Store in doc_metadata as JSON |
| Exits, Taps, Screenshots | Video interaction details | Store in doc_metadata as JSON |
| Media tags | Content tags | Similar to labels |
| Insights metrics (YouTube, subscribers, view time) | Platform-specific insights | Store in doc_metadata as JSON |
| Swipe up/down (Stories metric) | Story interaction data | Store in doc_metadata as JSON |

---

## 📋 Recommended Ingestion Strategy

### **Approach: Map to Documents + Store Extra Data in JSON**

1. **Direct Column Mapping** (39 columns)
   - Map Excel columns directly to documents table columns
   - Handle type conversions (FLOAT → INT, etc.)

2. **Metadata Storage** (94+ additional Excel columns)
   - Store unmapped Excel columns as JSON in `doc_metadata` field
   - Preserves all data for future analysis
   - Example structure:
     ```json
     {
       "created_timezone": "UTC +04:00",
       "profile_followers": 2105172,
       "sentiment": "positive",
       "reactions_breakdown": {
         "like": 100,
         "love": 50,
         "wow": 20
       },
       "video_metrics": {
         "10_second_views": 5000,
         "30_second_views": 3000,
         "completion_rate": 0.45
       }
     }
     ```

3. **System Columns**
   - `sheet_name`: "feb-2026" or "nov-2025"
   - `row_number`: 1, 2, 3... (row index in Excel)
   - `created_at`: CURRENT_TIMESTAMP
   - `updated_at`: CURRENT_TIMESTAMP
   - `embedding`: NULL (to be generated later)

---

## 🎯 Data Quality Notes

### **NULL/Empty Handling**

- **feb-2026.xlsx**: Many columns are NULL (especially video metrics for non-video content)
- **nov-2025.xlsx**: Fewer columns, focuses on main metrics
- **Strategy**: 
  - Keep NULL values as NULL in appropriate database columns
  - Store NULL counts in metadata for analysis

### **Date Handling**

- "Reported at": `2026-02-04 00:38:05` → Extract DATE as `2026-02-04`
- Most rows will have valid dates
- Type casting: DATETIME → DATE

### **Numeric Type Conversions**

- Excel stores numbers as FLOAT/DECIMAL
- Database expects INT for interaction counts
- Strategy: ROUND() during import, log any precision loss

---

## ✅ Column Count Verification

```
Excel feb-2026.xlsx:    133 columns  
Excel nov-2025.xlsx:     41 columns (subset)

Database documents:       73 total columns
├─ System fields:         6 (id, sheet_name, row_number, text, embedding, doc_metadata)
├─ Direct mappings:      39  ← Map from Excel
├─ Auto-generated:        4 (created_at, updated_at, timestamps)
└─ Metadata/JSON:        24  ← Store Excel overflow

Total mapped:            39 direct + 24 metadata = 63 active columns
Unmapped but stored:     94+ (in JSON metadata)
```

---

## 📍 Next Steps for User Review

**BEFORE RUNNING SEED SCRIPT, PLEASE CONFIRM:**

1. ✅ Are the **39 direct column mappings** correct?
2. ✅ Should **metadata overflow** be stored in `doc_metadata` as JSON?
3. ✅ Level of detail needed: Store ALL extra columns or only key metrics?
4. ✅ Any custom transformations needed for specific fields?
5. ✅ Date format: Should `published_date` be derived from `Reported at`?

**Example Transformation Rule** (for your approval):

```python
Row Processing:
  sheet_name = filename              # "feb-2026.xlsx" or "nov-2025.xlsx"
  row_number = row_index + 1         # 1-based row number
  text = f"{title} {content}"        # Combined searchable text
  
  Direct mappings:
  reported_at → published_date
  profile_name, platform, content_type, media_type → as-is
  total_reach, impressions, engagements → INT conversion
  
  JSON metadata includes:
  created_timezone, sentiment, reactions breakdown, video metrics, etc.
  
  embedding = NULL (to generate later with embedding service)
```

---

## 💾 Files Ready for Ingestion

✅ `data/analytics/feb-2026.xlsx` - Content sheet (5,634 rows)  
✅ `data/analytics/nov-2025.xlsx` - Content sheet (1,492 rows)  
**Total records to ingest: 7,126**

---

**Please review the mappings and confirm, then I'll proceed with the seed script!**
