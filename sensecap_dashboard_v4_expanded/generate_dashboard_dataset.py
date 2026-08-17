
"""Generate the expanded synthetic dataset used by app_exact_replica.py.

The dataset is intentionally synthetic. It is designed to exercise the
dashboard's geographic, sentiment, engagement, theme, weekly and ROI views.
No network access is required.
"""
import random
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

SEED = 20260809
N_ROWS = 12400
OUT = "sentiment_dashboard_dataset.csv"
random.seed(SEED)
np.random.seed(SEED)

REGIONS = [
("North America","United States","USA",38.0,-97.0),("North America","Canada","CAN",56.0,-106.0),
("North America","Mexico","MEX",23.6,-102.5),("South America","Brazil","BRA",-10.0,-55.0),
("South America","Argentina","ARG",-34.0,-64.0),("Europe","United Kingdom","GBR",55.0,-3.0),
("Europe","Germany","DEU",51.0,10.0),("Europe","France","FRA",46.2,2.2),
("Europe","Spain","ESP",40.2,-3.7),("Europe","Italy","ITA",42.8,12.8),
("Europe","Netherlands","NLD",52.1,5.3),("Europe","Sweden","SWE",62.0,15.0),
("Asia","India","IND",22.5,79.0),("Asia","Japan","JPN",36.2,138.3),
("Asia","South Korea","KOR",36.5,127.9),("Asia","Singapore","SGP",1.35,103.8),
("Asia","Australia","AUS",-25.0,133.0),("Asia","Philippines","PHL",12.9,122.0),
("Asia","Indonesia","IDN",-2.0,118.0),("Middle East","United Arab Emirates","ARE",24.0,54.0),
("Africa","South Africa","ZAF",-30.6,22.9),("Africa","Nigeria","NGA",9.1,8.7),
("Africa","Egypt","EGY",26.8,30.8),
]
PLATFORMS = ["YouTube","Reddit","Meta","X"]
PLATFORM_WEIGHTS = [0.42,0.22,0.20,0.16]
THEMES = ["Product Features","Customer Service","Story / Plot","Visual Quality",
          "Cast & Acting","Music / Score","Trailer Editing","Overall Hype"]
THEME_WEIGHTS = [0.15,0.08,0.16,0.14,0.12,0.10,0.12,0.13]
ROI_DRIVERS = ["Product Features","Customer Experience","Brand Value"]
ROI_WEIGHTS = [0.42,0.30,0.28]
POS = [
"This trailer's {theme} is incredible. It completely won me over.",
"Honestly, the {theme} is on another level. Can't wait for the release.",
"This is exactly what I wanted. The {theme} looks fantastic.",
"Goosebumps. The {theme} makes this trailer feel premium.",
"I've replayed this trailer so many times because of the {theme}.",
"The {theme} sold me instantly. This is going to be huge.",
]
NEU = [
"The {theme} looks fine so far, but I need to see more.",
"Not sure about the {theme} yet. Waiting for more information.",
"The {theme} is interesting, although the trailer doesn't show enough.",
"Mixed feelings about the {theme}; could go either way.",
"Hard to judge the {theme} from one trailer.",
]
NEG = [
"The {theme} is disappointing. I expected much more.",
"Not feeling the {theme} at all. It looks rushed.",
"The {theme} hurts the trailer for me. It needs improvement.",
"I was excited, but the {theme} is a major letdown.",
"The {theme} feels generic compared with the previous campaign.",
]

def sentiment():
    r = random.random()
    if r < 0.75:
        return "Positive", random.uniform(0.35, 0.98), random.choice(POS)
    if r < 0.90:
        return "Neutral", random.uniform(-0.12, 0.12), random.choice(NEU)
    return "Negative", random.uniform(-0.92, -0.25), random.choice(NEG)

def main():
    base = datetime(2026, 8, 9, 17, 30)
    rows = []
    region_weights = [0.09,0.04,0.035,0.025,0.035,0.06,0.05,0.045,0.035,0.03,0.025,0.02,
                      0.12,0.045,0.035,0.02,0.04,0.03,0.025,0.03,0.025,0.02,0.02]
    for i in range(1, N_ROWS + 1):
        label, score, template = sentiment()
        reg = random.choices(REGIONS, weights=region_weights)[0]
        theme = random.choices(THEMES, weights=THEME_WEIGHTS)[0]
        platform = random.choices(PLATFORMS, weights=PLATFORM_WEIGHTS)[0]
        days_ago = random.randint(0, 27)
        ts = base - timedelta(days=days_ago, hours=random.randint(0,23),
                               minutes=random.randint(0,59), seconds=random.randint(0,59))
        likes = max(0, int(np.random.lognormal(2.0, 1.0)))
        shares = max(0, int(np.random.lognormal(1.0, .85))) if random.random() < .72 else 0
        replies = max(0, int(np.random.lognormal(.8, .8))) if random.random() < .80 else 0
        engagement = likes + 2*shares + replies
        roi_driver = random.choices(ROI_DRIVERS, weights=ROI_WEIGHTS)[0]
        rows.append({
            "comment_id": f"fb_{i:06d}",
            "platform": platform,
            "region": reg[0], "country": reg[1], "country_code": reg[2],
            "language": "English", "content_type": random.choice(["Comment","Reply","Review","Quote Post","Reaction"]),
            "campaign": random.choice(["Global Trailer Launch","Creator Cut A/B","Product Reveal","Regional Teaser","Always-on Social"]),
            "text": template.format(theme=theme.lower()),
            "theme": theme, "sentiment_label": label, "sentiment_score": round(score,3),
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "likes": likes, "shares": shares, "replies": replies, "engagement": engagement,
            "roi_driver": roi_driver, "roi_value_usd": 0.0, "lat": reg[3], "lon": reg[4],
        })
    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    raw = np.maximum(df["engagement"].to_numpy() *
                     np.where(df["sentiment_label"].eq("Positive"), 2.4,
                              np.where(df["sentiment_label"].eq("Neutral"),1.0,.45)) *
                     np.random.uniform(.8,1.25,N_ROWS), 5)
    df["roi_value_usd"] = np.round(raw * (42552 / raw.sum()), 2)
    df.loc[df.index[-1],"roi_value_usd"] += round(42552 - df["roi_value_usd"].sum(), 2)
    df.to_csv(OUT, index=False)
    print(f"Wrote {len(df):,} rows to {OUT}")
    print(df["sentiment_label"].value_counts())
    print(f"Regions: {df['country'].nunique()} | ROI: ${df['roi_value_usd'].sum():,.2f}")

if __name__ == "__main__":
    main()
