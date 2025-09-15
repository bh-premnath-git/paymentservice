#!/bin/bash

# Universal Proto Generation Script with Enhanced Error Handling
# Works on all systems including PEP 668 protected environments

set -e

# Version configuration
PROTOBUF_VERSION="${PROTOBUF_VERSION:-6.31.1}"
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

# Check if ensurepip is available
check_ensurepip() {
    if ! $PYTHON_CMD -c "import ensurepip" 2>/dev/null; then
        echo "⚠️  ensurepip not available - cannot create virtual environment"
        echo "🔧 Detecting system and suggesting fix..."
        
        if command -v apt-get >/dev/null 2>&1; then
            PYTHON_VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
            echo "💡 Run: sudo apt install python${PYTHON_VERSION}-venv"
            echo "   Then re-run this script"
        elif command -v yum >/dev/null 2>&1; then
            echo "💡 Run: sudo yum install python3-pip python3-venv"
        elif command -v dnf >/dev/null 2>&1; then
            echo "💡 Run: sudo dnf install python3-pip python3-venv"
        elif command -v pacman >/dev/null 2>&1; then
            echo "💡 Run: sudo pacman -S python-pip python-virtualenv"
        else
            echo "💡 Install python3-venv package for your distribution"
        fi
        return 1
    fi
    return 0
}

# Attempt installation via pipx
try_pipx_install() {
    if command -v pipx >/dev/null 2>&1; then
        echo "📦 Using pipx to manage grpcio-tools..."
        
        if ! pipx list | grep -q grpcio-tools; then
            echo "📦 Installing grpcio-tools via pipx..."
            if pipx install grpcio-tools; then
                echo "✅ grpcio-tools installed via pipx"
            else
                echo "⚠️  pipx installation failed"
                return 1
            fi
        fi
        
        # Find pipx venv path
        PIPX_VENV_PATH=""
        if [ -d "$HOME/.local/share/pipx/venvs/grpcio-tools" ]; then
            PIPX_VENV_PATH="$HOME/.local/share/pipx/venvs/grpcio-tools"
        elif [ -d "$HOME/.local/pipx/venvs/grpcio-tools" ]; then
            PIPX_VENV_PATH="$HOME/.local/pipx/venvs/grpcio-tools"
        fi
        
        if [ -n "$PIPX_VENV_PATH" ] && [ -f "$PIPX_VENV_PATH/bin/python" ]; then
            USE_PYTHON="$PIPX_VENV_PATH/bin/python"
            echo "✅ Using pipx-managed grpcio-tools"
            return 0
        else
            echo "⚠️  Could not locate pipx grpcio-tools installation"
            return 1
        fi
    else
        return 1
    fi
}

# Attempt system installation with override
try_system_install() {
    echo "📦 Attempting system installation with override..."
    
    # First check if pip is available
    if ! $PYTHON_CMD -m pip --version >/dev/null 2>&1; then
        echo "⚠️  pip not available, trying to install..."
        if command -v apt-get >/dev/null 2>&1; then
            sudo apt-get update && sudo apt-get install -y python3-pip
        fi
    fi
    
    # Try different installation approaches
    local install_success=false
    
    # Method 1: --break-system-packages
    if $PYTHON_CMD -m pip install --user --break-system-packages --quiet protobuf==$PROTOBUF_VERSION grpcio-tools==$GRPC_TOOLS_VERSION 2>/dev/null; then
        install_success=true
    # Method 2: Without --break-system-packages (older systems)
    elif $PYTHON_CMD -m pip install --user --quiet protobuf==$PROTOBUF_VERSION grpcio-tools==$GRPC_TOOLS_VERSION 2>/dev/null; then
        install_success=true
    # Method 3: System packages (Ubuntu/Debian)
    elif command -v apt-get >/dev/null 2>&1; then
        echo "📦 Trying system package installation..."
        if sudo apt-get install -y python3-grpcio-tools python3-protobuf; then
            install_success=true
        fi
    fi
    
    if [ "$install_success" = true ]; then
        if $PYTHON_CMD -c "import grpc_tools.protoc" 2>/dev/null; then
            echo "✅ grpcio-tools installed successfully"
            USE_PYTHON="$PYTHON_CMD"
            return 0
        fi
    fi
    
    echo "⚠️  System installation failed"
    return 1
}

# Set up trap for cleanup on script exit
trap cleanup EXIT INT TERM

echo "🔍 Proto Generation Enhanced"
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
fi

# Method 3: Try creating virtual environment with enhanced error handling
if [ -z "$USE_PYTHON" ]; then
    echo "🔧 Attempting to create virtual environment..."
    
    # Check venv module availability
    if ! $PYTHON_CMD -m venv --help >/dev/null 2>&1; then
        echo "🔧 python-venv module not found"
        
        # Try to install python3-venv on supported systems
        if command -v apt-get >/dev/null 2>&1; then
            echo "🔧 Attempting to install python3-venv..."
            if sudo apt-get update && sudo apt-get install -y python3-venv; then
                echo "✅ python3-venv installed successfully"
            else
                echo "⚠️  Could not auto-install python3-venv"
            fi
        fi
        
        # Re-check after potential installation
        if ! $PYTHON_CMD -m venv --help >/dev/null 2>&1; then
            echo "⚠️  venv module still not available, trying alternatives..."
        fi
    fi
    
    # Check ensurepip availability before creating venv
    if $PYTHON_CMD -m venv --help >/dev/null 2>&1; then
        if ! check_ensurepip; then
            echo "❌ Cannot create virtual environment due to missing ensurepip"
            echo "🔄 Trying alternative installation methods..."
        else
            echo "📦 Creating virtual environment..."
            
            # Clean any existing broken venv
            rm -rf "$VENV_DIR" 2>/dev/null || true
            
            # Create new venv
            if $PYTHON_CMD -m venv "$VENV_DIR"; then
                if [ -f "$VENV_DIR/bin/activate" ]; then
                    source "$VENV_DIR/bin/activate"
                    VENV_ACTIVATED=true
                    
                    echo "📦 Installing grpcio-tools in virtual environment..."
                    python -m pip install --quiet --upgrade pip
                    
                    if python -m pip install --quiet protobuf==$PROTOBUF_VERSION grpcio-tools==$GRPC_TOOLS_VERSION; then
                        if python -c "import grpc_tools.protoc" 2>/dev/null; then
                            echo "✅ Virtual environment created successfully"
                            USE_PYTHON="python"
                        else
                            echo "⚠️  grpcio-tools import failed after installation"
                            deactivate
                            VENV_ACTIVATED=false
                        fi
                    else
                        echo "⚠️  Failed to install grpcio-tools in venv"
                        deactivate
                        VENV_ACTIVATED=false
                    fi
                else
                    echo "⚠️  Virtual environment creation failed"
                fi
            else
                echo "⚠️  Failed to create virtual environment"
            fi
        fi
    fi
    
    # Method 4: Try pipx if venv failed
    if [ -z "$USE_PYTHON" ]; then
        if try_pipx_install; then
            echo "✅ Using pipx installation"
        else
            # Method 5: Try system installation with override
            if try_system_install; then
                echo "✅ Using system installation"
            else
                echo "❌ All installation methods failed"
                echo ""
                echo "🔧 Manual installation options:"
                echo "1. sudo apt install python3-venv python3-pip  # For Debian/Ubuntu"
                echo "2. sudo apt install python3-grpcio-tools      # System-wide installation"
                echo "3. pipx install grpcio-tools                  # Isolated installation"
                echo "4. python3 -m pip install --user --break-system-packages grpcio-tools"
                echo ""
                echo "For Debian/Ubuntu specifically:"
                PYTHON_VERSION=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "3.12")
                echo "   sudo apt install python${PYTHON_VERSION}-venv"
                exit 1
            fi
        fi
    fi
fi

# Verify we have a working Python with grpcio-tools
if [ -z "$USE_PYTHON" ]; then
    echo "❌ No working Python environment with grpcio-tools found"
    exit 1
fi

# Final verification
if ! $USE_PYTHON -c "import grpc_tools.protoc" 2>/dev/null; then
    echo "❌ grpcio-tools import verification failed"
    exit 1
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
    echo "   source $VENV_DIR/bin/activate"
    echo "   python -c 'from your_proto_pb2 import YourMessage'"
else
    echo "   import sys"
    echo "   sys.path.insert(0, '$OUTPUT_DIR')"
    echo "   # Then import your generated modules"
    echo "   # Example: from your_proto_pb2 import YourMessage"
fi

echo ""
echo "🔧 Environment details:"
echo "  • Python: $PYTHON_CMD"
echo "  • gRPC tools: $USE_PYTHON"
if [ "$VENV_ACTIVATED" = true ]; then
    echo "  • Virtual env: $VENV_DIR"
fi

if [ $FAIL_COUNT -gt 0 ]; then
    exit 1
fi

exit 0