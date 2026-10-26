"""Release entry point; no check application or bootstrap credentials."""
import uvicorn

from backend.orchestrator import Config, create_application


def main():
    config = Config.from_environment()
    uvicorn.run(create_application(config), host=config.listen_host, port=8000,
                workers=1, access_log=False, log_level='warning',
                timeout_graceful_shutdown=130)


if __name__ == '__main__':
    main()
