# Day 5 Notes — Text Processing, SSH, Environment Variables

## Text Processing Tools

- `wc -l` — count lines in a file
- `grep` — search for patterns in files
  - `-i` case insensitive, `-v` invert match, `-c` count, `-r` recursive, `-E` extended regex
- `awk` — extract and filter by column. Fields are whitespace-split: `$1`, `$7`, `$9` etc.
  - `$0` = entire line, `$NF` = last field
- `sed` — find and replace: `sed 's/old/new/g' file`
  - `-i` edits the file in place
- `sort` — `-n` numeric, `-r` reverse, `-u` unique, `-k` by column
- `uniq -c` — count occurrences (must sort first)
- `cut` — extract columns by delimiter: `cut -d',' -f1`
- `tr` — translate/replace characters: `tr 'a-z' 'A-Z'`
- `|` — pipe, chains commands. Output of left becomes input of right

### The Core Pipeline Pattern
```bash
awk '{print $1}' access.log | sort | uniq -c | sort -rn | head -10
```
Used constantly for log analysis — extract field, sort, count, sort by count, show top N.

### Apache Combined Log Format
```
IP - - [timestamp timezone] "METHOD /path PROTOCOL" STATUS SIZE "referrer" "user-agent"
$1        $4       $5         $6    $7     $8         $9    $10
```
Status code = `$9`, URL = `$7`, IP = `$1`

---

## SSH

- **Password auth** — server asks for password. AWS disables this by default.
- **Key auth** — private key stays on your machine, public key goes on the server. More secure.
- `ssh-keygen -t ed25519 -C "email"` — generate a key pair
  - `~/.ssh/id_ed25519` = private key, never share
  - `~/.ssh/id_ed25519.pub` = public key, safe to share
- `ssh-copy-id -i ~/.ssh/id_ed25519.pub user@host` — installs your public key on a server
- `chmod 600 ~/.ssh/id_ed25519` — private key must be owner read/write only or SSH refuses
- `ssh-add --apple-use-keychain ~/.ssh/id_ed25519` — store passphrase in Mac keychain

### ~/.ssh/config
Aliases for SSH connections so you don't type full commands every time:
```
Host labvm
    HostName 172.19.241.100
    User dimi
    IdentityFile ~/.ssh/id_ed25519
```
Then just: `ssh labvm`

### SCP / rsync
- `scp file.txt user@host:~/destination/` — copy files over SSH
- `rsync -avz ~/folder/ user@host:~/folder/` — sync directories, only transfers changes
  - `-a` archive, `-v` verbose, `-z` compress, `-n` dry run

### SSH Tunneling
```bash
ssh -L 5432:localhost:5432 user@host
```
Forwards local port to remote port through SSH. Used to access private databases without exposing them publicly.

### SSH Agent
Holds your decrypted private key in memory so you don't retype passphrase every connection.

---

## Environment Variables

- Variables the OS passes to every process at startup
- `export VAR="value"` — makes variable available to child processes
- Only persists for the current shell session unless added to `~/.bashrc`
- `env` — see all current environment variables
- `echo $VAR` — print a variable's value
- `$PATH` — colon-separated list of directories the shell searches for commands

### Shell Config Files
- `~/.bashrc` — runs for every interactive shell (put aliases, exports, PATH additions here)
- `~/.bash_profile` — runs for login shells (SSH sessions). Best practice: source .bashrc from here
- `~/.zshrc` — equivalent of .bashrc on Mac (zsh is default)
- `source ~/.bashrc` — reload config without restarting terminal

### Why It Matters for DevOps
- **12-factor apps** — config lives in environment, not in code. Same codebase works in dev/staging/prod
- **Secrets management** — passwords and API keys set on the server, never hardcoded in scripts
- `os.environ.get("DB_PASSWORD")` in Python reads from the OS environment — the value is set on whichever machine runs the script, not in the code itself

---

## log_analyzer.py
Built a full Apache log parser in Python covering:
- `argparse` for command-line arguments
- Regex (`re`) to parse each log line into fields
- `collections.Counter` for counting IPs, URLs, status codes
- Error handling for missing files, malformed lines
- JSON output with `json.dumps()`
- Clean function structure with single-purpose functions and a simple `main()`

---

## Networking / Static IP
- Set static IP on VM via netplan: `/etc/netplan/00-installer-config.yaml`
- UTM bridged network uses `172.19.241.x` subnet — static IP must be in this range
- `chmod 600` on netplan config required or it throws warnings
