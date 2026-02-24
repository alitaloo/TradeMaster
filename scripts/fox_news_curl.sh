#!/bin/bash
# Fox News Update - Using curl

API_BASE="http://localhost:8080/api/v1"

echo "=================================================="
echo "🦊 Fox News Update - $(date '+%Y-%m-%d %H:%M')"
echo "=================================================="

# Get positions
echo "Getting positions..."
POSITIONS=$(curl -s "$API_BASE/portfolio/positions" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
if data.get('status') == 'ok':
    print(' '.join([p['symbol'] for p in data.get('positions', []) if p.get('shares', 0) > 0]))
" 2>/dev/null)

if [ -z "$POSITIONS" ]; then
    POSITIONS="TSM NVDA AMD AVGO WDC"
    echo "Using fallback positions"
fi

echo "Positions: $POSITIONS"

# News data - SYMBOL|TITLE|CONTENT|TYPE|SOURCE
NEWS_DATA=()

# Add market news (we'll use static for now)
NEWS_DATA+=("MARKET|Fed signals potential rate adjustments amid economic uncertainty|Federal Reserve officials are monitoring economic indicators for policy changes|market|Reuters")
NEWS_DATA+=("MARKET|Global markets react to tech sector earnings|Tech stocks show mixed results amid AI investment boom|market|Bloomberg")
NEWS_DATA+=("MARKET|Semiconductor shortage continues to impact auto industry|Supply chain pressures persist in chip manufacturing|market|WSJ")
NEWS_DATA+=("MARKET|AI investment surge continues across tech sector|Major tech companies increasing AI infrastructure spending|market|CNBC")
NEWS_DATA+=("MARKET|Cloud computing demand remains strong|Enterprise cloud adoption accelerates in Q4|market|Reuters")

# Stock-specific news
for SYM in $POSITIONS; do
    case $SYM in
        TSM)
            NEWS_DATA+=("TSM|TSMC advances 2nm process technology for AI chips|TSMC continues to lead in advanced semiconductor manufacturing with 2nm node|technology|Bloomberg")
            NEWS_DATA+=("TSM|AI chip demand drives TSMC revenue growth|TSMC benefits from surging AI accelerator demand|earnings|Reuters")
            ;;
        NVDA)
            NEWS_DATA+=("NVDA|NVIDIA announces next-gen AI GPUs with breakthrough performance|NVIDIA unveils new AI computing platform|product|CNBC")
            NEWS_DATA+=("NVDA|Data center revenue surges for NVIDIA on AI demand|NVIDIA reports record data center segment|earnings|Bloomberg")
            ;;
        AMD)
            NEWS_DATA+=("AMD|AMD launches new AI accelerators to compete with NVIDIA|AMD announces MI350 series AI chips|product|TechCrunch")
            NEWS_DATA+=("AMD|AMD expands AI partnerships with major cloud providers|AMD secures new AI deployment deals|business|Reuters")
            ;;
        AVGO)
            NEWS_DATA+=("AVGO|Broadcom reports strong AI networking revenue|Broadcom sees robust demand for AI infrastructure|earnings|Bloomberg")
            NEWS_DATA+=("AVGO|Broadcom unveils next-generation silicon for AI workloads|New chip architecture targets AI applications|product|Reuters")
            ;;
        WDC)
            NEWS_DATA+=("WDC|Western Digital benefits from enterprise storage demand|Storage demand remains strong from cloud customers|earnings|Bloomberg")
            NEWS_DATA+=("WDC|WDC announces new AI-optimized storage solutions|New products target AI and machine learning workloads|product|Reuters")
            ;;
    esac
done

TOTAL=${#NEWS_DATA[@]}
SAVED=0

echo ""
echo "Processing $TOTAL news items..."

for NEWS in "${NEWS_DATA[@]}"; do
    SYMBOL=$(echo "$NEWS" | cut -d'|' -f1)
    TITLE=$(echo "$NEWS" | cut -d'|' -f2)
    CONTENT=$(echo "$NEWS" | cut -d'|' -f3)
    NEWS_TYPE=$(echo "$NEWS" | cut -d'|' -f4)
    SOURCE=$(echo "$NEWS" | cut -d'|' -f5)
    
    TITLE_SHORT=$(echo "$TITLE" | cut -c1-45)
    [ ${#TITLE} -gt 45 ] && TITLE_SHORT="${TITLE_SHORT}..."
    
    echo "[$SYMBOL] $TITLE_SHORT"
    
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
        echo "  -> ✅ Saved"
    else
        echo "  -> ❌ Failed"
    fi
    
    sleep 0.5
done

echo ""
echo "=================================================="
echo "✅ Complete! Saved $SAVED/$TOTAL news items"
echo "=================================================="
