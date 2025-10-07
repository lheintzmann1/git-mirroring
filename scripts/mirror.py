#!/usr/bin/env python3
"""
GitHub to Codeberg Repository Mirroring Script

This script automatically mirrors GitHub repositories to Codeberg,
excluding repositories listed in the blacklist and repositories
belonging to organizations (only personal repositories are mirrored).
"""

import os
import sys
import time
import logging
import requests
from typing import List, Dict, Set
from github import Github, Auth
from git import Repo, GitCommandError
import tempfile
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mirror.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class RepositoryMirror:
    def __init__(self):
        """Initialize the repository mirror with required tokens and usernames."""
        self.github_token = os.getenv('GITHUB_TOKEN')
        self.codeberg_token = os.getenv('CODEBERG_TOKEN')
        self.github_username = os.getenv('GITHUB_ACTOR') or os.getenv('GH_USERNAME')
        self.codeberg_username = os.getenv('CODEBERG_USERNAME')
        
        if not all([self.github_token, self.codeberg_token, self.github_username, self.codeberg_username]):
            logger.error(f"Missing required environment variables:")
            logger.error(f"GITHUB_TOKEN: {'✓' if self.github_token else '✗'}")
            logger.error(f"CODEBERG_TOKEN: {'✓' if self.codeberg_token else '✗'}")
            logger.error(f"GITHUB_USERNAME (GITHUB_ACTOR): {'✓' if self.github_username else '✗'}")
            logger.error(f"CODEBERG_USERNAME: {'✓' if self.codeberg_username else '✗'}")
            sys.exit(1)
            
        auth = Auth.Token(self.github_token)
        self.github = Github(auth=auth)
        self.blacklist = self._load_blacklist()
        
    def _load_blacklist(self) -> Set[str]:
        """Load repository blacklist from file."""
        blacklist = set()
        try:
            with open('blacklist.txt', 'r') as f:
                for line in f:
                    repo_name = line.strip()
                    if repo_name and not repo_name.startswith('#'):
                        blacklist.add(repo_name)
            logger.info(f"Loaded blacklist with {len(blacklist)} repositories")
        except FileNotFoundError:
            logger.warning("blacklist.txt not found, proceeding without blacklist")
        return blacklist
    
    def _make_codeberg_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make an authenticated request to Codeberg API."""
        url = f"https://codeberg.org/api/v1{endpoint}"
        headers = {
            'Authorization': f'token {self.codeberg_token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.request(method, url, headers=headers, **kwargs)
        
        # Handle rate limiting
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            logger.warning(f"Rate limited, waiting {retry_after} seconds")
            time.sleep(retry_after)
            return self._make_codeberg_request(method, endpoint, **kwargs)
            
        return response
    
    def _repository_exists_on_codeberg(self, repo_name: str) -> bool:
        """Check if repository already exists on Codeberg."""
        response = self._make_codeberg_request('GET', f'/repos/{self.codeberg_username}/{repo_name}')
        return response.status_code == 200
    
    def _create_codeberg_repository(self, github_repo) -> bool:
        """Create a new repository on Codeberg."""
        data = {
            'name': github_repo.name,
            'description': github_repo.description or f"Mirror of {github_repo.full_name}",
            'private': github_repo.private,
            'auto_init': False
        }
        
        response = self._make_codeberg_request('POST', '/user/repos', json=data)
        
        if response.status_code == 201:
            logger.info(f"Created repository {github_repo.name} on Codeberg")
            return True
        elif response.status_code == 409:
            logger.info(f"Repository {github_repo.name} already exists on Codeberg")
            return True
        else:
            logger.error(f"Failed to create repository {github_repo.name}: {response.text}")
            return False
    
    def _mirror_repository(self, github_repo) -> bool:
        """Mirror a single repository from GitHub to Codeberg."""
        repo_name = github_repo.name
        
        logger.info(f"Mirroring repository: {repo_name}")
        
        # Create repository on Codeberg if it doesn't exist
        if not self._repository_exists_on_codeberg(repo_name):
            if not self._create_codeberg_repository(github_repo):
                return False
        
        # Clone and push repository
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Clone from GitHub
                github_url = f"https://{self.github_token}@github.com/{github_repo.full_name}.git"
                codeberg_url = f"https://{self.codeberg_token}@codeberg.org/{self.codeberg_username}/{repo_name}.git"
                
                logger.info(f"Cloning {github_repo.full_name}")
                repo = Repo.clone_from(github_url, temp_dir, mirror=True)
                
                # Add Codeberg remote
                codeberg_remote = repo.create_remote('codeberg', codeberg_url)
                
                # Push all branches and tags to Codeberg, excluding pull request refs
                logger.info(f"Pushing to Codeberg")
                try:
                    repo.git.push('codeberg', '--mirror')
                except GitCommandError as push_error:
                    # Check if the error is due to pull request refs being rejected
                    if 'refs/pull/' in str(push_error) and 'hook declined' in str(push_error):
                        logger.warning(f"Pull request refs rejected for {repo_name}, pushing branches and tags separately")
                        # Push all branches
                        repo.git.push('codeberg', '--all')
                        # Push all tags
                        repo.git.push('codeberg', '--tags')
                    else:
                        # Re-raise the error if it's not related to pull request refs
                        raise
                
                logger.info(f"Successfully mirrored {repo_name}")
                return True
                
            except GitCommandError as e:
                # Check if this is a partial success (some refs pushed successfully)
                if 'refs/pull/' in str(e) and ('hook declined' in str(e) or 'remote rejected' in str(e)):
                    # Count as success if main branches/tags were pushed despite PR ref failures
                    if 'new branch' in str(e) or 'new tag' in str(e):
                        logger.warning(f"Git push completed with PR ref warnings for {repo_name}: {e}")
                        return True
                logger.error(f"Git error while mirroring {repo_name}: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected error while mirroring {repo_name}: {e}")
                return False
    
    def get_repositories_to_mirror(self) -> List:
        """Get list of repositories to mirror, excluding blacklisted ones and organization repositories."""
        try:
            user = self.github.get_user()
            all_repos = list(user.get_repos())
            
            repos_to_mirror = []
            org_repos_skipped = 0
            
            for repo in all_repos:
                # Skip repositories that belong to organizations (not owned by the user)
                if repo.owner.login != self.github_username:
                    logger.info(f"Skipping organization repository: {repo.full_name} (owned by {repo.owner.login})")
                    org_repos_skipped += 1
                    continue
                    
                if repo.name not in self.blacklist:
                    repos_to_mirror.append(repo)
                else:
                    logger.info(f"Skipping blacklisted repository: {repo.name}")
            
            logger.info(f"Found {len(repos_to_mirror)} repositories to mirror (excluding {len(self.blacklist)} blacklisted and {org_repos_skipped} organization repositories)")
            return repos_to_mirror
            
        except Exception as e:
            logger.error(f"Error fetching repositories: {e}")
            return []
    
    def run_mirroring(self):
        """Run the complete mirroring process."""
        logger.info("Starting repository mirroring process")
        
        repositories = self.get_repositories_to_mirror()
        
        if not repositories:
            logger.warning("No repositories found to mirror")
            return
        
        successful_mirrors = 0
        failed_mirrors = 0
        
        for repo in repositories:
            try:
                if self._mirror_repository(repo):
                    successful_mirrors += 1
                else:
                    failed_mirrors += 1
                    
                # Add delay between repositories to respect rate limits
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Unexpected error processing {repo.name}: {e}")
                failed_mirrors += 1
        
        logger.info(f"Mirroring completed: {successful_mirrors} successful, {failed_mirrors} failed")
        
        # Only exit with error code if ALL repositories failed
        if successful_mirrors == 0 and failed_mirrors > 0:
            logger.error("All repositories failed to mirror")
            sys.exit(1)
        elif failed_mirrors > 0:
            logger.warning(f"Some repositories failed to mirror ({failed_mirrors} failed, {successful_mirrors} successful)")


def main():
    """Main entry point."""
    try:
        mirror = RepositoryMirror()
        mirror.run_mirroring()
    except KeyboardInterrupt:
        logger.info("Mirroring interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()