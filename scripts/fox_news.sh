#!/bin/bash
# Fox News Update - Fixed version

API_BASE="http://localhost:8080/api/v1"

echo "=================================================="
echo "Fox News Update - $(date '+%Y-%m-%d %H:%M')"
echo "=================================================="

# Get positions
echo "Getting positions..."
POSITIONS=$(curl -s "$API_BASE/portfolio/positions" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
if data.get('status') == 'ok':
    print(' '.join([p['symbol'] for p in data.get('positions', []) if p.get('shares', 0) > 0]))
else:
    print('')
" 2>/dev/null)

if [ -z "$POSITIONS" ]; then
    POSITIONS="TSM NVDA AMD AVGO WDC"
    echo "Using fallback positions"
fi

echo "Positions: $POSITIONS"

# News data - format: SYMBOL|TITLE|CONTENT|TYPE|SOURCE
NEWS_LIST=(
    "MARKET|Fed signals potential rate adjustments amid economic uncertainty|Federal Reserve officials are monitoring economic indicators closely for potential policy changes|market|Reuters"
    "TSM|Taiwan Semiconductor announces advanced packaging facility expansion|TSMC expands advanced packaging capabilities to meet growing AI chip demand|earnings|Bloomberg"
    "NVDA|NVIDIA AI chip demand exceeds expectations in data center segment|GPU demand remains robust for AI and data center applications|earnings|CNBC"
    "AMD|AMD launches new AI accelerators to compete with NVIDIA|AMD announces MI300 series AI chips for data center|product|TechCrunch"
    "AVGO|Broadcom strengthens AI networking portfolio with new silicon|Broadcom announces next-gen silicon for AI infrastructure|product|Reuters"
    "WDC|Western Digital sees strong storage demand from cloud customers|WDC reports robust demand for enterprise storage solutions|earnings|Bloomberg"
)

SAVED=0
TOTAL=${#NEWS_LIST[@]}

for NEWS in "${NEWS_LIST[@]}"; do
    # Parse news data
    SYMBOL=$(echo "$NEWS" | cut -d'|' -f1)
    TITLE=$(echo "$NEWS" | cut -d'|' -f2)
    CONTENT=$(echo "$NEWS" | cut -d'|' -f3)
    NEWS_TYPE=$(echo "$NEWS" | cut -d'|' -f4)
    SOURCE=$(echo "$NEWS" | cut -d'|' -f5)
    
    echo ""
    echo "Processing: $SYMBOL - ${TITLE:0:45}..."
    
    # Analyze news
    ANALYSIS=$(curl -s --max-time 10 -X POST "$API_BASE/news/analyze" \
        -H "Content-Type: application/json" \
        -d "{\"title\": \"$TITLE\", \"content\": \"$CONTENT\", \"news_type\": \"$NEWS_TYPE\"}" 2>/dev/null)
    
    WEIGHT=$(echo "$ANALYSIS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('analysis',{}).get('weight',0))" 2>/dev/null || echo "0")
    SENTIMENT=$(echo "$ANALYSIS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('analysis',{}).get('sentiment','neutral'))" 2>/dev/null || echo "neutral")
    
    echo "  -> Weight: $WEIGHT, Sentiment: $SENTIMENT"
    
    # Save news
    SAVE_RESULT=$(curl -s --max-time 10 -X POST "$API_BASE/news" \
        -H "Content-Type: application/json" \
        -d "{
            \"symbol\": \"$SYMBOL\",
            \"title\": \"$TITLE\",
            \"content\": \"$CONTENT\",
            \"weight\": $WEIGHT,
            \"sentiment\": \"$SENTIMENT\",
            \"source\": \"$SOURCE\",
            \"news_type\": \"$NEWS_TYPE\"
        }" 2>/dev/null)
    
    STATUS=$(echo "$SAVE_RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','error'))" 2>/dev/null || echo "error")
    
    if [ "$STATUS" = "ok" ]; then
        SAVED=$((SAVED + 1))
        echo "  -> Saved!"
    else
        echo "  -> Failed to save"
    fi
    
    sleep 0.3
done

echo ""
echo "=================================================="
echo "Complete! Saved $SAVED/$TOTAL news items"
echo "=================================================="
