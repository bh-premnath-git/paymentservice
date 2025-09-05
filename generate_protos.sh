#!/bin/bash

# Universal Proto Generation Script with Proper Cleanup
# Works on all systems including PEP 668 protected environments

set -e

# Version configuration
PROTOBUF_VERSION="${PROTOBUF_VERSION:-5.28.3}"
GRPC_TOOLS_VERSION="${GRPC_TOOLS_VERSION:-1.74.0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROTOS_DIR="$SCRIPT_DIR/protos"
OUTPUT_DIR="$SCRIPT_DIR"
VENV_DIR="$SCRIPT_DIR/.proto_venv"
VENV_ACTIVATED=false

# Cleanup function to ensure proper venv deactivation
cleanup() {
    local exit_code=$?
    
    # Deactivate virtual environment if it was activated
    if [ "$VENV_ACTIVATED" = true ] && [ -n "$VIRTUAL_ENV" ]; then
        echo ""
        echo "🔒 Cleaning up virtual environment..."
        deactivate 2>/dev/null || true
        echo "✅ Virtual environment deactivated"
    fi
    
    # Clean any temporary files
    rm -f /tmp/proto_gen_* 2>/dev/null || true
    
    if [ $exit_code -eq 0 ]; then
        echo "👍 Script completed successfully"
    else
        echo "⚠️  Script exited with code: $exit_code"
    fi
    
    exit $exit_code
}

# Set up trap for cleanup on script exit
trap cleanup EXIT INT TERM

echo "🔍 Proto Generation"
echo "📁 Protos: $PROTOS_DIR"
echo "📁 Output: $OUTPUT_DIR"
echo "🔧 Protobuf version: $PROTOBUF_VERSION"
echo "🔧 gRPC tools version: $GRPC_TOOLS_VERSION"

# Check protos directory
if [ ! -d "$PROTOS_DIR" ]; then
    echo "❌ Error: Protos directory not found at $PROTOS_DIR"
    exit 1
fi

# Find Python
PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "❌ Error: Python not found"
    exit 1
fi

echo "🐍 Using: $PYTHON_CMD"

# Method 1: Check if grpcio-tools is already available globally
if $PYTHON_CMD -c "import grpc_tools.protoc" 2>/dev/null; then
    echo "✅ grpcio-tools already available globally"
    USE_PYTHON="$PYTHON_CMD"

# Method 2: Try using existing virtual environment
elif [ -f "$VENV_DIR/bin/python" ] && [ -f "$VENV_DIR/bin/activate" ]; then
    echo "📦 Found existing virtual environment, checking..."
    
    # Activate venv temporarily to check
    source "$VENV_DIR/bin/activate"
    VENV_ACTIVATED=true
    
    if python -c "import grpc_tools.protoc" 2>/dev/null; then
        echo "✅ Using existing virtual environment"
        USE_PYTHON="python"
    else
        echo "⚠️  Virtual environment exists but missing grpcio-tools"
        deactivate
        VENV_ACTIVATED=false
        rm -rf "$VENV_DIR"
        echo "🔄 Will create fresh virtual environment..."
    fi

# Method 3: Try creating virtual environment
fi

if [ -z "$USE_PYTHON" ]; then
    # Check if we can create venv
    if $PYTHON_CMD -m venv --help >/dev/null 2>&1; then
        echo "📦 Creating virtual environment..."
        
        # Clean any existing broken venv
        rm -rf "$VENV_DIR" 2>/dev/null || true
        
        # Create new venv
        $PYTHON_CMD -m venv "$VENV_DIR"
        
        if [ -f "$VENV_DIR/bin/activate" ]; then
            source "$VENV_DIR/bin/activate"
            VENV_ACTIVATED=true
            
            echo "📦 Installing grpcio-tools in virtual environment..."
            python -m pip install --quiet --upgrade pip
            python -m pip install --quiet protobuf==$PROTOBUF_VERSION grpcio-tools==$GRPC_TOOLS_VERSION
            
            if python -c "import grpc_tools.protoc" 2>/dev/null; then
                echo "✅ Virtual environment created successfully"
                USE_PYTHON="python"
            else
                echo "❌ Failed to install grpcio-tools in venv"
                deactivate
                VENV_ACTIVATED=false
                exit 1
            fi
        else
            echo "❌ Failed to create virtual environment"
        fi
        
    # Method 4: Try pipx
    elif command -v pipx >/dev/null 2>&1; then
        echo "📦 Using pipx to manage grpcio-tools..."
        
        if ! pipx list | grep -q grpcio-tools; then
            echo "📦 Installing grpcio-tools via pipx..."
            pipx install grpcio-tools
        fi
        
        GRPC_TOOLS_PATH="$HOME/.local/pipx/venvs/grpcio-tools"
        if [ -d "$GRPC_TOOLS_PATH" ]; then
            USE_PYTHON="$GRPC_TOOLS_PATH/bin/python"
            echo "✅ Using pipx-managed grpcio-tools"
        else
            echo "❌ Failed to install via pipx"
            exit 1
        fi
        
    # Method 5: Use --break-system-packages flag
    elif $PYTHON_CMD -m pip --version >/dev/null 2>&1; then
        echo "📦 Installing grpcio-tools (user directory with override)..."
        
        $PYTHON_CMD -m pip install --user --break-system-packages --quiet protobuf==$PROTOBUF_VERSION grpcio-tools==$GRPC_TOOLS_VERSION
        
        if $PYTHON_CMD -c "import grpc_tools.protoc" 2>/dev/null; then
            echo "✅ grpcio-tools installed successfully"
            USE_PYTHON="$PYTHON_CMD"
        else
            echo "❌ Failed to install grpcio-tools"
            exit 1
        fi
        
    else
        echo "❌ Cannot automatically install grpcio-tools"
        echo ""
        echo "Please install manually using one of these methods:"
        echo "1. sudo apt install python3.12-venv  # Then run this script again"
        echo "2. sudo apt install python3-grpcio-tools"
        echo "3. pipx install grpcio-tools"
        exit 1
    fi
fi

# Find proto files
echo ""
echo "🔍 Finding proto files..."
PROTO_FILES=($(find "$PROTOS_DIR" -name "*.proto" -type f | sort))

if [ ${#PROTO_FILES[@]} -eq 0 ]; then
    echo "❌ No .proto files found in $PROTOS_DIR"
    exit 1
fi

echo "📋 Found ${#PROTO_FILES[@]} proto file(s):"
for proto_file in "${PROTO_FILES[@]}"; do
    rel_path="${proto_file#$PROTOS_DIR/}"
    echo "  📄 $rel_path"
done

# Generate Python files
echo ""
echo "⚙️  Generating Python gRPC files..."
SUCCESS_COUNT=0
FAIL_COUNT=0

for proto_file in "${PROTO_FILES[@]}"; do
    rel_path="${proto_file#$PROTOS_DIR/}"
    echo "🔧 Processing: $rel_path"
    
    # Create output directory structure if needed
    dir_path=$(dirname "$rel_path")
    if [ "$dir_path" != "." ]; then
        mkdir -p "$OUTPUT_DIR/$dir_path"
    fi
    
    # Run protoc
    if $USE_PYTHON -m grpc_tools.protoc \
        --python_out="$OUTPUT_DIR" \
        --grpc_python_out="$OUTPUT_DIR" \
        --proto_path="$PROTOS_DIR" \
        "$proto_file" 2>/dev/null; then
        echo "  ✅ Generated successfully"
        ((SUCCESS_COUNT++))
    else
        echo "  ❌ Failed to generate"
        echo "  Error details:"
        $USE_PYTHON -m grpc_tools.protoc \
            --python_out="$OUTPUT_DIR" \
            --grpc_python_out="$OUTPUT_DIR" \
            --proto_path="$PROTOS_DIR" \
            "$proto_file"
        ((FAIL_COUNT++))
    fi
done

# Create __init__.py files for all generated Python packages
echo ""
echo "📦 Creating Python package structure..."

# Find all directories that contain generated _pb2.py files
GENERATED_DIRS=($(find "$OUTPUT_DIR" -name "*_pb2.py" -exec dirname {} \; | sort -u))

INIT_COUNT=0
for dir in "${GENERATED_DIRS[@]}"; do
    # Create __init__.py in the directory and all parent directories up to OUTPUT_DIR
    current_dir="$dir"
    while [ "$current_dir" != "$OUTPUT_DIR" ] && [ "$current_dir" != "/" ]; do
        init_file="$current_dir/__init__.py"
        if [ ! -f "$init_file" ]; then
            touch "$init_file"
            ((INIT_COUNT++))
            rel_init="${init_file#$OUTPUT_DIR/}"
            echo "  📄 Created: $rel_init"
        fi
        current_dir="$(dirname "$current_dir")"
    done
done

# List generated files
echo ""
echo "📁 Generated files:"
GENERATED_FILES=($(find "$OUTPUT_DIR" \( -name "*_pb2.py" -o -name "*_pb2_grpc.py" \) | sort))

if [ ${#GENERATED_FILES[@]} -le 10 ]; then
    for file in "${GENERATED_FILES[@]}"; do
        rel_file="${file#$OUTPUT_DIR/}"
        echo "  ✅ $rel_file"
    done
else
    echo "  Generated ${#GENERATED_FILES[@]} files (showing first 5):"
    for i in {0..4}; do
        rel_file="${GENERATED_FILES[$i]#$OUTPUT_DIR/}"
        echo "  ✅ $rel_file"
    done
    echo "  ... and $((${#GENERATED_FILES[@]} - 5)) more"
fi

echo ""
echo "🎉 Proto generation completed!"
echo "📊 Summary:"
echo "  • Total proto files: ${#PROTO_FILES[@]}"
echo "  • Successfully generated: $SUCCESS_COUNT"
if [ $FAIL_COUNT -gt 0 ]; then
    echo "  • Failed: $FAIL_COUNT"
fi
echo "  • Python files created: ${#GENERATED_FILES[@]}"
echo "  • Package __init__.py files: $INIT_COUNT"

# Show package structure
echo ""
echo "📦 Python package structure:"
find "$OUTPUT_DIR" -name "__init__.py" | head -5 | while read init_file; do
    package_dir="$(dirname "$init_file")"
    rel_package="${package_dir#$OUTPUT_DIR/}"
    if [ -n "$rel_package" ]; then
        echo "  📦 $rel_package/"
    fi
done

echo ""
echo "💡 Usage in Python:"
if [ "$VENV_ACTIVATED" = true ]; then
    echo "   # With virtual environment activated:"
    echo "   python -c 'from your_proto_pb2 import YourMessage'"
else
    echo "   import sys"
    echo "   sys.path.insert(0, '$OUTPUT_DIR')"
    echo "   # Then import your generated modules"
    echo "   # Example: from your_proto_pb2 import YourMessage"
fi

if [ $FAIL_COUNT -gt 0 ]; then
    exit 1
fi

exit 0