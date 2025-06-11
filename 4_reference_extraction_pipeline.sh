#!/bin/bash
# Simple reference-based species extraction pipeline
# OUTPUT: CSV with columns: doi, species, abundance_or_biomass, number, location, distance_from_seed, title

show_help() {
    echo "Usage: $0 [options]"
    echo
    echo "Simple reference-based species extraction"
    echo "OUTPUT: doi, species, abundance_or_biomass, number, location, distance_from_seed, title"
    echo
    echo "Options:"
    echo "  -s, --seed-paper FILE        Seed PDF paper (required)"
    echo "  -ck, --claude-key KEY        Claude API key (required)"
    echo "  -sk, --scopus-key KEY        Scopus API key (required)"
    echo "  -o, --output-dir DIR         Output directory (default: ./reference_data)"
    echo "  -mp, --max-papers NUM        Maximum papers to process (default: 20)"
    echo "  -md, --max-depth NUM         Maximum reference depth (default: 2)"
    echo "  -kw, --keywords WORDS        Keywords to filter references (comma-separated)"
    echo "  -h, --help                   Show this help"
    echo
    echo "Reference depth explanation:"
    echo "  Distance 0: Seed paper"
    echo "  Distance 1: Direct references from seed paper"
    echo "  Distance 2: References of references"
    echo "  Distance N: N degrees of separation from seed"
    echo
    echo "Examples:"
    echo "  $0 -s paper.pdf -ck KEY -sk KEY -kw \"mammal,wildlife\""
    echo "  $0 -s paper.pdf -ck KEY -sk KEY -md 3 -mp 50"
    echo
}

# Default values
SEED_PAPER=""
CLAUDE_KEY=""
SCOPUS_KEY=""
OUTPUT_DIR="./reference_data"
MAX_PAPERS=20
MAX_DEPTH=2
KEYWORDS=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--seed-paper)
            SEED_PAPER="$2"
            shift 2
            ;;
        -ck|--claude-key)
            CLAUDE_KEY="$2"
            shift 2
            ;;
        -sk|--scopus-key)
            SCOPUS_KEY="$2"
            shift 2
            ;;
        -o|--output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -mp|--max-papers)
            MAX_PAPERS="$2"
            shift 2
            ;;
        -md|--max-depth)
            MAX_DEPTH="$2"
            shift 2
            ;;
        -kw|--keywords)
            KEYWORDS="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Check required parameters
if [ -z "$SEED_PAPER" ]; then
    echo "❌ Error: Seed paper is required"
    show_help
    exit 1
fi

if [ ! -f "$SEED_PAPER" ]; then
    echo "❌ Error: Seed paper file '$SEED_PAPER' does not exist"
    exit 1
fi

if [ -z "$CLAUDE_KEY" ]; then
    echo "❌ Error: Claude API key is required"
    show_help
    exit 1
fi

if [ -z "$SCOPUS_KEY" ]; then
    echo "❌ Error: Scopus API key is required"
    show_help
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Generate output filename
SEED_NAME=$(basename "$SEED_PAPER" .pdf)
SEED_NAME=$(echo "$SEED_NAME" | tr ' ' '_' | tr -cd '[:alnum:]_-')
OUTPUT_CSV="$OUTPUT_DIR/${SEED_NAME}_species_data.csv"

echo
echo "🔬 SIMPLE REFERENCE-BASED SPECIES EXTRACTION"
echo "============================================="
echo "📄 Seed paper: $SEED_PAPER"
echo "📤 Output: $OUTPUT_CSV"
echo "📊 Max papers: $MAX_PAPERS"
echo "📏 Max depth: $MAX_DEPTH"
if [ ! -z "$KEYWORDS" ]; then
    echo "🔍 Keywords filter: $KEYWORDS"
fi
echo "🔑 Claude API: configured"
echo "🔑 Scopus API: configured"
echo
echo "📋 Reference exploration:"
echo "  Distance 0: Seed paper"
echo "  Distance 1: Direct references"
if [ "$MAX_DEPTH" -ge 2 ]; then
    echo "  Distance 2+: References of references"
fi
echo "============================================="
echo

# Build command arguments
PYTHON_ARGS="--seed-paper \"$SEED_PAPER\" --output \"$OUTPUT_CSV\" --claude-key \"$CLAUDE_KEY\" --scopus-key \"$SCOPUS_KEY\" --max-papers $MAX_PAPERS --max-depth $MAX_DEPTH"

if [ ! -z "$KEYWORDS" ]; then
    PYTHON_ARGS="$PYTHON_ARGS --keywords \"$KEYWORDS\""
fi

# Run extraction
eval "python3 3_reference_based_extractor.py $PYTHON_ARGS"

# Check results
if [ -f "$OUTPUT_CSV" ]; then
    echo
    echo "✅ EXTRACTION COMPLETED SUCCESSFULLY!"
    echo
    echo "📊 RESULTS:"
    
    # Count entries
    TOTAL_ENTRIES=$(($(wc -l < "$OUTPUT_CSV") - 1))
    echo "📄 Total species entries: $TOTAL_ENTRIES"
    
    # Show file info
    echo "📁 Output file: $OUTPUT_CSV"
    echo "📏 File size: $(ls -lh "$OUTPUT_CSV" | awk '{print $5}')"
    
    # Show first few lines
    echo
    echo "📋 Sample output:"
    head -3 "$OUTPUT_CSV"
    
    echo
    echo "🎉 SUCCESS! Species data saved to: $OUTPUT_CSV"
else
    echo
    echo "❌ EXTRACTION FAILED!"
    echo "No output file was created."
    exit 1
fi
