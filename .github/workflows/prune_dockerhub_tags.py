#!/usr/bin/python3

import argparse
import requests
import subprocess
import sys

docker_hub_repos_url = 'https://hub.docker.com/v2/repositories/{0}/tags/'
docker_hub_login_url = 'https://hub.docker.com/v2/users/login/'

parser = argparse.ArgumentParser(
    description='Uses Docker Hub credentials to prune tags without corresponding branches in the origin repository.')

parser.add_argument('--user', '-u', dest='user',
                    action='store', required=True)
parser.add_argument('--pass', '-p', dest='password',
                    action='store', required=True)
parser.add_argument('--repo', '-r', dest='repo',
                    action='store', required=True)
args = parser.parse_args()

branch_cmd = "git branch --remotes".split()
branches = subprocess.run(branch_cmd, text=True,
                          capture_output=True).stdout.replace(' ', '').split()
origin_branches = []
for branch in branches:
    if branch.startswith("origin") and not branch.startswith("origin/HEAD"):
        clean_branch = branch.replace("origin/", "")
        if clean_branch == "master":
            origin_branches.append("latest")
        else:
            origin_branches.append(clean_branch)

docker_hub_creds = {'username': args.user, 'password': args.password}
headers = {'Content-Type': 'application/json'}
docker_hub_token = requests.post(
    docker_hub_login_url, headers=headers, json=docker_hub_creds).json()['token']
headers = {"Authorization": "JWT {0}".format(docker_hub_token)}
docker_tags = requests.get(
    docker_hub_repos_url.format(args.repo), headers=headers).json()

docker_tag_names = []
for tag in docker_tags["results"]:
    docker_tag_names.append(tag['name'])

failed_deletions = 0
successful_deletions = 0
preserved_tags = 0
for tag in docker_tag_names:
    if tag not in origin_branches:
        delete_tag = requests.delete(
            docker_hub_repos_url.format(args.repo) + tag, headers=headers)
        if delete_tag.status_code != 200:
            print("Failed to delete {0}:{1} at {3}".format(
                args.repo, tag, delete_tag.url))
            failed_deletions += 1
        else:
            print("Tag {0}:{1} deleted successfully.".format(args.repo, tag))
            successful_deletions += 1
    else:
        print("Tag '{0}:{1}' has a matching branch, leaving '{0}:{1}' in place.".format(
            args.repo, tag))
        preserved_tags += 1
print("Done checking for old tags on '{0}', {1} tags deleted, {2} tags failed to delete, {3} tags left in place. Exiting.".format(
    args.repo, successful_deletions, failed_deletions, preserved_tags))
sys.exit(0)
