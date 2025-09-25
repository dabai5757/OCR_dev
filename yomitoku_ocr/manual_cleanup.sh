#!/bin/bash

# 手动清理OCR static文件脚本
# 可以根据需要调整清理策略

STATIC_DIR="/static"

echo "=== OCR Static Files Manual Cleanup ==="
echo "Static directory: $STATIC_DIR"

if [ ! -d "$STATIC_DIR" ]; then
    echo "ERROR: Static directory $STATIC_DIR does not exist"
    exit 1
fi

# 显示当前状态
echo ""
echo "Current status:"
DIR_COUNT=$(find "$STATIC_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
echo "- Total directories: $DIR_COUNT"

if command -v du >/dev/null 2>&1; then
    SIZE=$(du -sh "$STATIC_DIR" 2>/dev/null | cut -f1)
    echo "- Total size: $SIZE"
fi

echo ""
echo "Cleanup options:"
echo "1. Remove files older than 1 day"
echo "2. Remove files older than 6 hours"
echo "3. Remove files older than 1 hour"
echo "4. Remove all files (DANGER!)"
echo "5. Show file list only"
echo "0. Cancel"

read -p "Choose option (0-5): " choice

case $choice in
    1)
        echo "Removing files older than 1 day..."
        find "$STATIC_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +1 -exec rm -rf {} \; 2>/dev/null
        ;;
    2)
        echo "Removing files older than 6 hours..."
        find "$STATIC_DIR" -mindepth 1 -maxdepth 1 -type d -mmin +360 -exec rm -rf {} \; 2>/dev/null
        ;;
    3)
        echo "Removing files older than 1 hour..."
        find "$STATIC_DIR" -mindepth 1 -maxdepth 1 -type d -mmin +60 -exec rm -rf {} \; 2>/dev/null
        ;;
    4)
        read -p "Are you sure you want to remove ALL files? (yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            echo "Removing all files..."
            rm -rf "$STATIC_DIR"/*
        else
            echo "Cancelled."
            exit 0
        fi
        ;;
    5)
        echo "File list:"
        ls -la "$STATIC_DIR"
        exit 0
        ;;
    0)
        echo "Cancelled."
        exit 0
        ;;
    *)
        echo "Invalid option."
        exit 1
        ;;
esac

# 显示清理后的状态
echo ""
echo "After cleanup:"
NEW_DIR_COUNT=$(find "$STATIC_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
REMOVED_COUNT=$((DIR_COUNT - NEW_DIR_COUNT))
echo "- Remaining directories: $NEW_DIR_COUNT"
echo "- Removed directories: $REMOVED_COUNT"

if command -v du >/dev/null 2>&1; then
    NEW_SIZE=$(du -sh "$STATIC_DIR" 2>/dev/null | cut -f1)
    echo "- New size: $NEW_SIZE"
fi

echo "Cleanup completed!"
