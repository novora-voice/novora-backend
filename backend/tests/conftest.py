import os


os.environ["NOVORA_DATABASE_URL"] = "sqlite://"
os.environ["NOVORA_JWT_SECRET"] = "novora-test-jwt-secret"
os.environ["NOVORA_SECRET_ENCRYPTION_KEY"] = "novora-test-encryption-secret"
os.environ["NOVORA_DISABLE_EVALUATION_WORKER"] = "true"
