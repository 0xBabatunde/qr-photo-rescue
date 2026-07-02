# Publishing

This local repo is ready to publish as a public GitHub repository.

## Option A: GitHub CLI

Install and authenticate `gh`, then run from this repo:

```bash
gh repo create 0xBabatunde/qr-photo-rescue \
  --public \
  --source=. \
  --remote=origin \
  --push \
  --description "Recover damaged photographed QR codes by reconstructing the module grid from visible geometry."
```

## Option B: GitHub Web UI + SSH Push

1. Create an empty public repository at:

   ```text
   https://github.com/new
   ```

2. Use:

   ```text
   Repository name: qr-photo-rescue
   Visibility: Public
   ```

3. Then push this local repo:

   ```bash
   git remote add origin git@github.com:0xBabatunde/qr-photo-rescue.git
   git push -u origin main
   ```

SSH authentication for `git@github.com` was confirmed locally as `0xBabatunde`.
