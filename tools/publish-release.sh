#!/usr/bin/env bash
# Invoked by CI with the token confined to the publishing job.
set -euo pipefail

channel=$1
tag=$2
version=$3
commit=$4
assets=$5

case "$channel" in
  development|stable) ;;
  *) echo "Unknown release channel" >&2; exit 1 ;;
esac

if gh release view "$tag" >/dev/null 2>&1; then
  if [[ "$channel" == stable ]]; then
    echo "Stable release $tag already exists; no assets or metadata were changed." >&2
    exit 1
  fi
  gh release upload "$tag" "$assets"/* --clobber
  gh release edit "$tag" --prerelease --latest=false
  exit 0
fi

options=(--target "$commit" --title "MintTweaks $version")
if [[ "$channel" == development ]]; then
  options+=(--prerelease --latest=false)
  notes="Préversion de développement du commit $commit. Inclut le paquet Debian, les sources correspondantes et SHA256SUMS. Cette construction ne constitue pas une version stable validée sous Linux Mint."
else
  options+=(--verify-tag)
  notes="Version stable $version issue du commit $commit, publiée à partir du tag explicite $tag. Inclut le paquet Debian, les sources correspondantes et SHA256SUMS."
fi
gh release create "$tag" "$assets"/* "${options[@]}" --notes "$notes"
