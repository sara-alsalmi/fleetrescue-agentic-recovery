# FleetRescue Agent Instructions

## Security Rules
- NEVER open, read, search, print, copy, edit, or expose `.env`.
- NEVER inspect or display API keys or secret values.
- Use `.env.example` to understand configuration.
- The application may load `.env` internally at runtime.
- Never include secrets in prompts, logs, or test results.
- Never make paid API calls without explicit user approval.

## Testing Rules
- Run offline tests first.
- Never inspect `.env` to verify configuration.
- Check API connectivity only through the application.
- Report model ID, tool calls, actions, verification results, token usage, and estimated cost.
- Stop if any unexpected error risks exposing credentials.