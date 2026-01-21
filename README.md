# Claude Code on Snowflake Cortex

Run [Claude Code](https://docs.anthropic.com/en/docs/claude-code) using Snowflake's Cortex AI service as the backend—uses Snowflake credits instead of Claude API credits.

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   Claude Code   │ ──▶  │  LiteLLM Proxy  │ ──▶  │ Snowflake Cortex│
│   (Terminal)    │      │  (localhost)    │      │   (Claude API)  │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

## Why This Exists

Snowflake Cortex provides access to Claude models through their platform. This setup:

- **Proxies** Claude Code requests through LiteLLM to Snowflake's API
- **Auto-refreshes** JWT tokens every 50 minutes (Snowflake tokens expire in 1 hour)
- **Patches** a LiteLLM compatibility issue with Snowflake's API

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.10+ | Anaconda or Homebrew |
| Node.js | 18+ | For PM2 process manager |
| Snowflake | — | `ACCOUNTADMIN` role or ability to alter your user |

---

## Setup

### Step 1: Install Dependencies

```bash
# Install Claude Code
curl -fsSL https://claude.ai/install.sh | bash
source ~/.zshrc  # or ~/.bashrc

# Install Python packages
pip install 'litellm[proxy]' cryptography pyjwt

# Install PM2 (process manager)
npm install -g pm2
```

### Step 2: Generate RSA Key Pair

```bash
mkdir -p ~/.ssh

# Generate private key (unencrypted PKCS8 format)
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/.ssh/snowflake_key.p8 -nocrypt

# Generate public key
openssl rsa -in ~/.ssh/snowflake_key.p8 -pubout -out ~/.ssh/snowflake_key.pub

# Secure the private key
chmod 600 ~/.ssh/snowflake_key.p8
```

### Step 3: Register Key with Snowflake

Copy your public key:

```bash
cat ~/.ssh/snowflake_key.pub
```

In Snowflake (Snowsight), run:

```sql
ALTER USER YOUR_USERNAME SET RSA_PUBLIC_KEY='<paste_key_content_here>';
```

> Only paste the content between `-----BEGIN PUBLIC KEY-----` and `-----END PUBLIC KEY-----`

### Step 4: Apply LiteLLM Patch

Snowflake's API doesn't support `max_tokens`, so we patch LiteLLM to rename it.

**Option A: Automated (Recommended)**

```bash
python patches/apply_patch.py
```

**Option B: Manual Patch**

If the automated patch fails, you can manually edit LiteLLM:

1. Open the file:

```bash
nano $(pip show litellm | grep Location | cut -d: -f2 | xargs)/litellm/llms/openai/openai.py
```

2. Search for `async def acompletion` (`Ctrl+W` in nano)

3. Find the line calling `self.make_openai_chat_completion_request` and paste this block **immediately BEFORE** that line:

```python
        # --- HACK: FORCE SNOWFLAKE COMPATIBILITY ---
        if "max_tokens" in data:
            data["max_completion_tokens"] = data.pop("max_tokens")
        # -------------------------------------------
```

4. Repeat for `async def astreaming` function if needed

5. Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`)

### Step 5: Configure auto_refresh.py

Edit `auto_refresh.py` with your Snowflake credentials:

```python
# Your Snowflake Account (use HYPHENS, not underscores)
# Example: "SFSENORTHAMERICA-MYORG-AWS-USW2" 
ACCOUNT = "YOUR_ACCOUNT_ID"

# Your Snowflake Username
USER = "YOUR_USERNAME"
```

### Step 6: Start Services

```bash
# Start the token refresher (generates litellm_config.yaml with fresh JWT)
pm2 start $(which python3) --name token-refresher -- $(pwd)/auto_refresh.py

# Wait 5 seconds for litellm_config.yaml to be created
sleep 5

# Start the LiteLLM proxy
pm2 start $(which litellm) --name claude-proxy --interpreter $(which python3) -- --config $(pwd)/litellm_config.yaml --port 8001

# Save process list (survives reboot)
pm2 save
```

### Step 7: Configure Claude Code

Before launching Claude, configure it to use your local proxy instead of Anthropic's servers. This bypasses the login screen.

**1. Mark onboarding as complete:**

```bash
echo '{"hasCompletedOnboarding": true}' > ~/.claude.json
```

**2. Point Claude to your local proxy:**

```bash
claude config set anthropicBaseUrl http://127.0.0.1:8001
```

**3. Set the API key (must match `master_key` in config):**

```bash
claude config set anthropicApiKey sk-local-dev-1234
```

**4. Whitelist localhost:**

```bash
claude config set allowSite 127.0.0.1:8001
```

### Step 8: Launch Claude

```bash
claude
```

---

## Architecture

```
                                    ┌──────────────────────────────┐
                                    │      token-refresher         │
                                    │   (regenerates JWT every     │
                                    │        50 minutes)           │
                                    └──────────────┬───────────────┘
                                                   │
                                                   ▼
┌──────────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│ Claude Code  │────▶│   LiteLLM    │────▶│litellm_config │────▶│  Snowflake   │
│   CLI        │     │    Proxy     │     │  (auto-gen)   │     │   Cortex     │
└──────────────┘     └──────────────┘     └───────────────┘     └──────────────┘
     :8001                                                        Claude 4.5
```

**Two PM2 processes run:**
1. `token-refresher` — Generates fresh JWT tokens and writes `litellm_config.yaml`
2. `claude-proxy` — LiteLLM server that routes requests to Snowflake

## Available Models

| Claude Code Model | Maps To | Snowflake Model |
|-------------------|---------|-----------------|
| `claude-sonnet-4-5-20250929` | → | `claude-sonnet-4-5` |
| `claude-haiku-4-5-20251001` | → | `claude-haiku-4-5` |

## Commands

```bash
# Check status
pm2 status

# View logs
pm2 logs claude-proxy
pm2 logs token-refresher

# Restart services
pm2 restart all

# Stop everything
pm2 stop all
```

## Troubleshooting

### "max_tokens is not supported"
The LiteLLM patch wasn't applied. Run:
```bash
python patches/apply_patch.py
pm2 restart claude-proxy
```

### "JWT token is invalid"
Your Snowflake public key isn't registered. In Snowflake:
```sql
ALTER USER YOUR_USERNAME SET RSA_PUBLIC_KEY='...';
```

### Token expires after 1 hour
Ensure `token-refresher` is running:
```bash
pm2 status token-refresher
```

## Limitations

- Snowflake Cortex may have different rate limits than Anthropic's API
- The LiteLLM patch is temporary and will be overwritten on updates
- Token refresh requires the private key to remain on disk

## License

MIT

## Acknowledgments

- [Anthropic](https://anthropic.com) for Claude
- [LiteLLM](https://github.com/BerriAI/litellm) for the proxy layer
- [Snowflake](https://snowflake.com) for Cortex AI
