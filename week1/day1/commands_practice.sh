#!/bin/bash
# Day 1: Linux Commands Practice

echo "=== Navigation Practice ==="
pwd
echo "Current directory listed:"
ls -la

echo ""
echo "=== File Creation Practice ==="
mkdir -p practice/subdirectory
touch practice/file1.txt practice/file2.txt
echo "Files created:"
tree practice/ 2>/dev/null || ls -R practice/

echo ""
echo "=== File Operations Practice ==="
cp practice/file1.txt practice/file1_backup.txt
mv practice/file2.txt practice/renamed.txt
echo "After operations:"
ls -l practice/

echo ""
echo "Practice complete!"
