#!/bin/bash
echo "Creating test files..."
touch secret.txt public.txt script.sh

chmod 600 secret.txt
chmod 644 public.txt  
chmod 755 script.sh

echo "Permissions set:"
ls -l *.txt *.sh

rm -f secret.txt public.txt script.sh
echo "Demo complete!"
