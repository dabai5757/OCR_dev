#!/bin/bash

# OCR static文件清理脚本
# 清理超过24小时的OCR处理结果文件

STATIC_DIR="/static"
LOG_FILE="/app/cleanup.log"

# 日志函数
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

# 检查static目录是否存在
if [ ! -d "$STATIC_DIR" ]; then
    log_message "ERROR: Static directory $STATIC_DIR does not exist"
    exit 1
fi

log_message "Starting cleanup of OCR static files..."

# 统计清理前的文件数量
BEFORE_COUNT=$(find "$STATIC_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
log_message "Found $BEFORE_COUNT directories before cleanup"

# 删除超过24小时的目录（基于目录名的时间戳）
# 目录格式: YYYYMMDD_HHMMSS_xxxxxxxx
find "$STATIC_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +1 -exec rm -rf {} \; 2>/dev/null

# 也可以基于目录的修改时间删除
# find "$STATIC_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +1 -exec rm -rf {} \;

# 统计清理后的文件数量
AFTER_COUNT=$(find "$STATIC_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
CLEANED_COUNT=$((BEFORE_COUNT - AFTER_COUNT))

log_message "Cleanup completed: $CLEANED_COUNT directories removed, $AFTER_COUNT remaining"

# 显示剩余空间
if command -v df >/dev/null 2>&1; then
    DISK_USAGE=$(df -h "$STATIC_DIR" | tail -1 | awk '{print $5}')
    log_message "Disk usage after cleanup: $DISK_USAGE"
fi

# 如果剩余目录过多，发出警告
if [ "$AFTER_COUNT" -gt 100 ]; then
    log_message "WARNING: $AFTER_COUNT directories remaining. Consider more aggressive cleanup."
fi

log_message "Cleanup script finished"