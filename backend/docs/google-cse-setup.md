# Google Custom Search Engine (CSE) Setup Guide

This guide walks through setting up a Google Custom Search Engine for the Agentic Beast platform to enable AI-powered web searches scoped to [The National News](https://thenationalnews.com).

## Overview

Google Custom Search Engine allows us to:
- Search only within `thenationalnews.com` domain
- Use real-time web index data
- Integrate via Google Custom Search JSON API
- Track search quotas and costs (100 free searches/day)

## Prerequisites

- Google Cloud Project (create one at [Google Cloud Console](https://console.cloud.google.com/))
- Admin access to the project for API enablement
- Billing account enabled (optional charges apply after free tier)

## Step-by-Step Setup

### Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top
3. Select **"NEW PROJECT"**
4. Enter Project Name: `agentic-beast-cse` (or your choice)
5. Click **"CREATE"**
6. Wait for the project to initialize, then select it

### Step 2: Enable the Custom Search API

1. In the Cloud Console, navigate to **APIs & Services** > **Library**
2. Search for `"Custom Search API"`
3. Click on **Custom Search API**
4. Click **ENABLE**
5. Wait a few seconds for the API to enable

### Step 3: Create an API Key

1. In the Cloud Console, navigate to **APIs & Services** > **Credentials**
2. Click **+ CREATE CREDENTIALS** at the top
3. Select **API Key**
4. A dialog appears with your new API key
5. Copy the key and save it somewhere safe (you'll need this for `GOOGLE_CSE_API_KEY`)
6. Optional: Click **RESTRICT KEY** to set restrictions:
   - Application restrictions: Select **HTTP referrers** (web sites)
   - Add your domain (e.g., `thenationalnews.com`)
   - API restrictions: Select **Restrict key** and enable only **Custom Search API**

### Step 4: Create a Custom Search Engine

1. Go to [Google Programmable Search Engine](https://programmablesearchengine.google.com/)
2. Sign in with the same Google Account used for the Cloud Project
3. Click **Create** to create a new search engine
4. Fill in the form:
   - **Name**: `The National News Search`
   - **Sites to search**: Enter `thenationalnews.com`
   - Leave other options as default
5. Click **CREATE**
6. On the next screen, you'll see your **Search Engine ID** (also called **CX ID**)
7. Copy the Search Engine ID and save it (you'll need this for `GOOGLE_CSE_ID`)

### Step 5: Configure Agentic Beast

Update your `.env` file (or deployment configuration) with:

```bash
# Google Custom Search Configuration
GOOGLE_CSE_API_KEY=<your-api-key-from-step-3>
GOOGLE_CSE_ID=<your-search-engine-id-from-step-4>
GOOGLE_CSE_SITE=thenationalnews.com
GOOGLE_CSE_DAILY_LIMIT=100  # Adjust based on your quota needs
```

### Step 6: Test the Integration

1. Ensure the backend is running
2. Call the search endpoint via the chat interface or directly:

```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "breaking news"}'
```

Expected response:
```json
{
  "results": [
    {
      "title": "Article Title",
      "url": "https://thenationalnews.com/...",
      "snippet": "Summary of the article...",
      "position": 1
    }
  ],
  "search_metadata": {
    "total_results": 1234,
    "execution_time_ms": 245
  }
}
```

## Quota & Limits

- **Free Tier**: 100 searches per day
- **Paid Tier**: Up to 10,000 searches per day (charges apply after free tier)
- **Query Length**: Max 2,048 characters
- **Results per Query**: Max 10 results (API returns 1-10)

### Monitoring Usage

1. In [Google Cloud Console](https://console.cloud.google.com/), go to **APIs & Services** > **Quotas**
2. Filter for "Custom Search API"
3. View daily usage and quota details
4. Set up alerts in **Billing** > **Budgets & alerts** to be notified when approaching quota limits

## Troubleshooting

### Error: "API key not valid. Please pass a valid API key."
- Verify `GOOGLE_CSE_API_KEY` is correct in `.env`
- Ensure the API key has **Custom Search API** enabled
- Check that the key hasn't been revoked in Cloud Console

### Error: "Invalid Programmable Search Engine ID."
- Verify `GOOGLE_CSE_ID` is correct in `.env`
- Confirm the CSE was created in [Programmable Search Engine](https://programmablesearchengine.google.com/)
- Ensure the CSE is enabled (not deleted/archived)

### Error: "Daily quota exceeded"
- Your search count exceeded `GOOGLE_CSE_DAILY_LIMIT` for the day
- Quotas reset daily at midnight UTC
- Upgrade to the paid tier to increase limits
- Check current usage in Cloud Console Quotas

### No Results Returned
- Verify the website (`thenationalnews.com`) is indexed by Google
- Test in Google Search to confirm the domain is searchable
- Ensure CSE still includes the site in **Sites to search** settings

## Advanced Configuration

### Multiple Domains

If you need to search multiple domains, edit your CSE:

1. Go to [Programmable Search Engine Settings](https://programmablesearchengine.google.com/controlpanel/all)
2. Click your search engine name
3. In **Basics**, edit **Sites to search**
4. Add additional domains (one per line):
   ```
   thenationalnews.com/*
   otherdomain.com/*
   ```

### Custom Refinements (Optional)

Create faceted search with custom refinements:

1. In CSE Settings, go to **Advanced**
2. Add custom refinements (e.g., "Breaking News", "Opinion")
3. Filter searches by category in production

## References

- [Google Custom Search API Documentation](https://developers.google.com/custom-search/v1)
- [Programmable Search Engine](https://programmablesearchengine.google.com/)
- [Google Cloud API Quotas](https://cloud.google.com/docs/quotas)
- [Custom Search Pricing](https://www.google.com/cse/manage)

## Support

For issues, contact:
- Google Cloud Support: https://cloud.google.com/support
- API Status: https://status.cloud.google.com/
- Agentic Beast Team: [team contact]
