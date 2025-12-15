# homebrew-brew-tools

This repository contains two related projects for managing and querying Homebrew package installations:

1. **`brew-tools/`** - The source repository containing the Python tools
2. **`homebrew-brew-tools/`** - The Homebrew tap repository for installing via `brew`

## Tools Overview

### `brew-index`
Indexes all Homebrew packages (formulae and casks) installed on your system and creates a persistent JSON index (`installs_index.json`) in your Homebrew repository. The index tracks:
- Package names and versions
- Installation paths
- First installation dates
- Optional GitHub commit history enrichment

### `brew-first-installs`
Queries the index created by `brew-index` to find packages that were first installed within a specific time window.

## Installation

### Method 1: Local Installation (Recommended for Development)

1. Clone this repository:
   ```bash
   git clone https://github.com/newalexandria/homebrew-brew-tools.git
   cd homebrew-brew-tools
   ```

2. Run the setup script:
   ```bash
   cd brew-tools
   ./scripts/setup.sh
   ```

   This installs the executables to `~/.local/bin/`. Make sure `~/.local/bin` is in your `PATH`:
   ```bash
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc  # or ~/.bashrc
   source ~/.zshrc
   ```

   Or manually copy the executables:
   ```bash
   mkdir -p ~/.local/bin
   cp brew-tools/bin/* ~/.local/bin/
   chmod +x ~/.local/bin/brew-index ~/.local/bin/brew-first-installs
   ```

### Method 2: Homebrew Tap Installation (Once Published)

Once the tap is published to GitHub, you can install via Homebrew:

```bash
brew tap newalexandria/brew-tools
brew install newalexandria/brew-tools/brew-index
brew install newalexandria/brew-tools/brew-first-installs
```

## Usage

### Step 1: Create the Index

First, run `brew-index` to scan your Homebrew installations and create the index:

```bash
brew-index
```

This creates `installs_index.json` in your Homebrew repository (typically `$(brew --repository)/installs_index.json`).

**Optional: Enrich with GitHub History**

If you have the GitHub CLI (`gh`) installed and authenticated, you can enrich the index with repository commit dates:

```bash
brew-index --enrich
```

This queries GitHub to find when each formula was first added to its tap repository. Note: This can take a while as it makes API calls for each package.

**Optional: Include Available Packages**

To also index packages that are available but not currently installed (added in the last year):

```bash
brew-index --available
```

You can combine flags:
```bash
brew-index --enrich --available
```

### Step 2: Query the Index

Use `brew-first-installs` to find packages installed within a time window:

```bash
# Find packages first installed between 30 and 7 days ago
brew-first-installs 30 7

# Find packages first installed in the last 7 days
brew-first-installs 7 0

# Output as JSON
brew-first-installs 30 7 --json

# Show detailed brew info for each match
brew-first-installs 30 7 --info
```

**Arguments:**
- `X` - Older bound (days ago)
- `Y` - Newer bound (days ago)
- `--json` - Output raw JSON array instead of formatted table
- `--info` - Show `brew info` output for each matching package

## Testing Functionality

### Basic Functionality Test

1. **Create an index:**
   ```bash
   brew-index
   ```
   Expected: Creates `installs_index.json` in your Homebrew repository. Check with:
   ```bash
   ls -la $(brew --repository)/installs_index.json
   ```

2. **Query recent installs:**
   ```bash
   brew-first-installs 365 0
   ```
   Expected: Shows a table of packages first installed in the last year.

3. **Test JSON output:**
   ```bash
   brew-first-installs 30 0 --json | jq .
   ```
   Expected: JSON array of matching packages.

### Test Help Commands

Both tools support `--help`:
```bash
brew-index --help
brew-first-installs --help
```

### Test GitHub Enrichment (Optional)

If you have `gh` installed:
```bash
brew-index --enrich
```
Expected: Progress messages showing GitHub API calls and enrichment results.

### Verify Installation

Check that both tools are available:
```bash
which brew-index
which brew-first-installs
```

Both should point to `~/.local/bin/` (for local install) or `/opt/homebrew/bin/` (for tap install).

## Repository Structure

```
homebrew-brew-tools/
├── brew-tools/              # Source repository
│   ├── bin/                 # Executable scripts
│   │   ├── brew-index
│   │   └── brew-first-installs
│   ├── scripts/             # Setup scripts
│   ├── .github/workflows/   # CI/CD workflows
│   └── README.md            # Tool-specific documentation
│
├── homebrew-brew-tools/     # Homebrew tap repository
│   └── Formula/             # Homebrew formula definitions
│       ├── brew-index.rb
│       └── brew-first-installs.rb
│
└── README.md                # This file
```

## Requirements

- **Python 3.11+** - Both tools are Python scripts
- **Homebrew** - Required for package management
- **GitHub CLI (`gh`)** - Optional, for enrichment feature
- **macOS** - Homebrew is primarily for macOS (though Linux support exists)

## Troubleshooting

### Index file not found
If `brew-first-installs` reports the index file is missing, run `brew-index` first to create it.

### Permission denied
Ensure the executables have execute permissions:
```bash
chmod +x ~/.local/bin/brew-index ~/.local/bin/brew-first-installs
```

### Command not found
Make sure `~/.local/bin` is in your PATH. Add to your shell config:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### GitHub enrichment fails
If `--enrich` fails, ensure:
- `gh` is installed: `brew install gh`
- You're authenticated: `gh auth status`
- You have internet connectivity

## Contributing

This repository contains both the tool source code and the Homebrew tap definitions. When making changes:

1. Update the tools in `brew-tools/bin/`
2. Update the version in `brew-tools/VERSION` if needed
3. Update the Formula files in `homebrew-brew-tools/Formula/` if installation changes are needed
4. Test locally before pushing

## License

MIT License - See `brew-tools/LICENSE` for details.

