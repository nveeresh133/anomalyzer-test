import re
from typing import Dict, Any

class DataRedactor:
    """
    Sanitizes Kubernetes telemetry and logs to remove sensitive tokens, passwords, 
    API keys, certificates, and private env variables before sending context to LLMs.
    """
    
    SECRET_KEYWORDS = re.compile(
        r"(password|passwd|secret|token|key|api[_-]?key|auth|bearer|credentials|private[_-]?key)",
        re.IGNORECASE
    )

    PATTERNS = [
        # Bearer tokens & JWTs
        (re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
        # AWS Access Key IDs & Secret Keys
        (re.compile(r"(AKIA|ASIA)[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
        # Generic API Keys / RSA Private Keys
        (re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
        # Basic Auth Passwords in URLs (http://user:pass@host)
        (re.compile(r"(https?://[a-zA-Z0-9_\-\.]+):([^@\s]+)@"), r"\1:[REDACTED_PASS]@"),
        # Key=Value or "key": "value" patterns for passwords/secrets
        (re.compile(r'(?i)(password|secret|token|api_key|access_key|auth_token)\s*[:=]\s*["\']?([^"\'\s;]+)["\']?'), r'\1=[REDACTED]'),
    ]

    @classmethod
    def scrub_text(cls, text: str) -> str:
        """Applies regex pattern replacements to obscure secrets in text logs."""
        if not text:
            return ""
        
        scrubbed = text
        for pattern, replacement in cls.PATTERNS:
            scrubbed = pattern.sub(replacement, scrubbed)
        return scrubbed

    @classmethod
    def sanitize_env_vars(cls, env_list: list) -> list:
        """Sanitizes environment variables list from container specs."""
        sanitized = []
        for env in env_list:
            if isinstance(env, dict):
                name = env.get("name", "")
                if cls.SECRET_KEYWORDS.search(name):
                    sanitized.append({"name": name, "value": "[REDACTED]"})
                else:
                    sanitized.append(env)
            else:
                sanitized.append(env)
        return sanitized

    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively scrub keys matching secret keywords in dictionaries."""
        sanitized = {}
        for key, val in data.items():
            if cls.SECRET_KEYWORDS.search(str(key)):
                sanitized[key] = "[REDACTED]"
            elif isinstance(val, dict):
                sanitized[key] = cls.sanitize_dict(val)
            elif isinstance(val, str):
                sanitized[key] = cls.scrub_text(val)
            else:
                sanitized[key] = val
        return sanitized
