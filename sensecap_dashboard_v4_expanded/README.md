# Sensecap — Pixel-closer Streamlit Sentiment Dashboard

This version is tuned against the supplied Sensecap dashboard screenshot. It keeps the existing synthetic dataset schema while adding a much closer visual system: compact top navigation, warm off-white canvas, rounded cards, orange geographic hero panel, AI analysis card, KPI strip, ROI donut, word cloud and weekly mentions.

## Run

```bash
python -m venv venv
# Windows
venv\\Scripts\\activate
# macOS/Linux
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Dataset

The bundled CSV contains 12,400 synthetic audience records with geography, sentiment, engagement, theme and ROI fields. Replace it with an equivalent CSV or upload one through the page.

## Interactions

- Dashboard / Trends / ROI Analysis / Reports navigation
- Platform, region, theme and date filters
- Hoverable geographic sentiment map
- Interactive Plotly trend and ROI charts
- CSV report download
- Sortable audience table
- Responsive layout for smaller screens
- CSS micro-animations: card hover lift, orange-panel sheen and animated topic bars

The numbers in the bundled dataset are synthetic and are intended for POC/demo presentation only.

### Upload-first behavior

The dashboard is intentionally **locked until a CSV is uploaded** through the Streamlit file uploader. The bundled `sentiment_dashboard_dataset.csv` is provided as an optional example only and is **not loaded automatically**.

Once a CSV is uploaded, the dashboard validates the required `platform`, `text`, and `timestamp` columns and then renders the full Sensecap-style interface.
