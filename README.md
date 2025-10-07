# GitHub to Codeberg Repository Mirroring

This repository automatically mirrors all your GitHub repositories to Codeberg using GitHub Actions.

## Features

- Automatic mirroring of all public and private repositories
- Blacklist support to exclude specific repositories
- Scheduled daily mirroring with GitHub Actions
- Secure handling of authentication tokens
- Detailed logging and error reporting

## Setup

### Prerequisites

1. A GitHub account with repositories to mirror
2. A Codeberg account
3. Personal access tokens for both platforms

### Installation

1. **Fork or clone this repository**

2. **Generate access tokens:**
   - **GitHub**: Go to Settings → Developer settings → Personal access tokens → Generate new token
     - Required scopes: `repo`, `read:org`
   - **Codeberg**: Go to Settings → Applications → Generate New Token
     - Required scopes: `repository`, `organization`

3. **Configure repository secrets:**
   Go to your repository Settings → Secrets and variables → Actions, then add:
   - `GITHUB_TOKEN`: Your GitHub personal access token
   - `CODEBERG_TOKEN`: Your Codeberg personal access token
   - `GITHUB_USERNAME`: Your GitHub username
   - `CODEBERG_USERNAME`: Your Codeberg username

4. **Configure the blacklist:**
   Edit the `blacklist.txt` file to add repositories you don't want to mirror (one per line)

5. **Enable GitHub Actions:**
   Go to the Actions tab and enable workflows for this repository

## Configuration

### Blacklist

Edit `blacklist.txt` to exclude repositories from mirroring. Add one repository name per line:

```text
git-mirroring
private-config
sensitive-repo
```

### Schedule

The mirroring runs daily at 2 AM UTC by default. You can modify the schedule in `.github/workflows/mirror.yml`:

```yaml
schedule:
  - cron: '0 2 * * *'  # Daily at 2 AM UTC
```

### Manual Trigger

You can manually trigger the mirroring process:

1. Go to the Actions tab
2. Select "Mirror Repositories"
3. Click "Run workflow"

## How It Works

1. The GitHub Action fetches all repositories from your GitHub account
2. Filters out repositories listed in the blacklist
3. For each repository:
   - Creates the repository on Codeberg if it doesn't exist
   - Sets up the mirror configuration
   - Pushes all branches and tags to Codeberg

## Troubleshooting

### Common Issues

1. **Repository already exists on Codeberg**: The script will skip creation and update the existing repository
2. **Permission denied**: Check that your tokens have the correct scopes
3. **Rate limiting**: The script includes delays to respect API rate limits

### Logs

Check the Actions tab for detailed logs of each mirroring run.

## Contributing

Feel free to submit issues and enhancement requests!

## License

MIT License - see [LICENSE](LICENSE) file for details.