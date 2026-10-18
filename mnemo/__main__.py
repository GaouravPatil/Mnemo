import os

import uvicorn


def main():
    uvicorn.run(
        "mnemo.api:create_app",
        factory=True,
        host=os.environ.get("MNEMO_HOST", "127.0.0.1"),
        port=int(os.environ.get("MNEMO_PORT", "8000")),
        reload=os.environ.get("MNEMO_RELOAD", "1").strip().lower() not in ("0", "false", "no"),
    )


if __name__ == "__main__":
    main()
