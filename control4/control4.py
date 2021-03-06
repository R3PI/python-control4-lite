# -*- coding:utf-8 -*-

import aiohttp
import logging
import time
import asyncio
import traceback

_LOGGER = logging.getLogger(__name__)


class Control4RetryError(TimeoutError):
    pass


class Control4TimeoutError(TimeoutError):
    pass


def retry(times=20, timeout_secs=10):
    def func_wrapper(f):
        async def wrapper(self, *args, **kwargs):
            start_time = time.time()

            for t in range(times):
                try:
                    self._stats['requests'] += 1
                    return await f(self, *args, **kwargs)
                except (aiohttp.ClientError, ConnectionError) as exc:
                    self._stats['errors'] += 1

                    _LOGGER.debug('Control4 error: %s, %s', str(exc), repr(traceback.format_exc()))

                    # if isinstance(exc, aiohttp.ClientResponseError):
                    traceback.print_exc()

                    if timeout_secs is not None:
                        if time.time() - start_time > timeout_secs:
                            raise Control4TimeoutError()

                    await asyncio.sleep(0.1 * t)

            raise Control4RetryError
        return wrapper
    return func_wrapper


class Control4(object):
    def __init__(self, url, session=None, proxy=None):
        _LOGGER.debug('init: %s', url)
        self._url = url
        self._session = session
        self._proxy = proxy
        self._stats = {'errors': 0, 'requests': 0}

    async def on(self, device_id):
        return await self.issue_command(device_id, "ON")

    async def off(self, device_id):
        return await self.issue_command(device_id, "OFF")

    async def set_level(self, device_id, level):
        return await self.issue_command(device_id, "SET_LEVEL", {"LEVEL": level})

    async def issue_command(self, device_id, command, params=None):
        if params is None:
            params = {}

        _LOGGER.debug('issue_command: cmd %s, device %d, params %s, url %s', command, device_id, str(params), self._url)

        json_request = {'command': command, 'deviceid': device_id, 'params': params}

        return await self._post_request(json_request)

    async def get(self, device_id, variable_id):
        _LOGGER.debug('get: device_id %d, variable_id %d', device_id, variable_id)

        query_params = {'deviceid': device_id, 'variableid': variable_id}

        return await self._get_request(query_params)

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            connector = aiohttp.TCPConnector(force_close=True)
            self._session = aiohttp.ClientSession(connector=connector)

        return self._session

    @retry()
    async def _post_request(self, json_request):
        async with self._get_session().post(self._url, json=json_request, proxy=self._proxy) as r:
            result = await r.text()

            _LOGGER.debug('issue_command: (%d) %s -- %s', r.status, str(result), str(r.request_info))
            print("Result", r.status, str(result), str(r.request_info))
            r.raise_for_status()

            return result

    @retry()
    async def _get_request(self, query_params):
        async with self._get_session().get(self._url, params=query_params, proxy=self._proxy) as r:

            r.raise_for_status()

            result = await r.json(content_type=None)
            _LOGGER.debug('get response for (%s): (%d) %s -- %s', r.url, r.status, str(result), str(r.request_info))
            return result['variablevalue']
