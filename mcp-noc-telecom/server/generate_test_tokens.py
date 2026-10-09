from datetime import datetime, timedelta, timezone
import jwt

from server.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRATION_MINUTES, ROLE_HIERARCHY


def generate_token(user: str, role: str) -> str:
    payload = {
        "user": user,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRATION_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


if __name__ == "__main__":
    print(f"Jetons valides {JWT_EXPIRATION_MINUTES} minutes.\n")
    for role in ROLE_HIERARCHY:
        token = generate_token(user=f"test-{role}", role=role)
        print(f"--- Role : {role} ---")
        print(token)
        print()
