import asyncio
import logging.config
import signal
from typing import Any, Optional, Union

from asyncio_socks_server.config import BASE_LOGO, SOCKS_SERVER_PREFIX, Config
from asyncio_socks_server.logger import error_logger, gen_log_config, logger
from asyncio_socks_server.proxyman import ProxyMan

HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)


class SocksServer:
    def __init__(
        self,
        config: Union[str, dict, Any] = None,
        env_prefix: Optional[str] = SOCKS_SERVER_PREFIX,
        **config_args,
    ):
        """
        Initialize the SOCKS server with the provided configuration.

        Args:
            config: Configuration for the server.
            env_prefix: Prefix for environment variables.
            **config_args: Additional configuration arguments.
        """
        self.loop = asyncio.get_event_loop() # similar to epoll in C
        self.config = Config()
        self.config.update_config(config)
        self.config.load_environment_vars(env_prefix)
        self.config.update_config(config_args)

        self.__init_logger()
        self.__init_proxyman()

    def __init_logger(self):
        log_config = gen_log_config(self.config)
        logging.config.dictConfig(log_config)

    def __init_proxyman(self):
        self.proxyman = ProxyMan(self.config)

    async def shut_down(self):
        logger.info("Waiting for background tasks to cancel")

        # stop accepting new connections
        await self.proxyman.close_server()
        # get all tasks except the current one, because it's the shutdown task
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in tasks]
        # awit the tasks cancellation
        await asyncio.gather(*tasks, return_exceptions=True)

        self.loop.stop()

    def run(self):
        # start the server
        self.loop.run_until_complete(self.proxyman.start_server())

        # for stop signals like SIGINT and SIGTERM, a shutdown task should be added.
        for s in HANDLED_SIGNALS:
            self.loop.add_signal_handler(
                s, lambda s=s: asyncio.create_task(self.shut_down())
            )

        logger.info(
            f"Server launched on" f" {self.config.LISTEN_HOST,self.config.LISTEN_PORT}"
        )

        # start the event loop util the server is stopped
        self.loop.run_forever()
        self.loop.close()

        logger.info("Server stopped")
