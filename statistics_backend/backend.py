#!/usr/bin/env python3
#
#  backend.py
"""
Base backend class.
"""
#
#  Copyright © 2023-2025 Dominic Davis-Foster <dominic@davis-foster.co.uk>
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
#  EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
#  MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#  IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
#  DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
#  OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
#  OR OTHER DEALINGS IN THE SOFTWARE.
#

# stdlib
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import date
from typing import Any, Dict, Iterator, Optional

# 3rd party
from domdf_python_tools.paths import PathPlus
from influxdb_client.client.influxdb_client import InfluxDBClient

__all__ = ["Backend"]


class Backend(ABC):
	"""
	A backend for obtaining data from InfluxDB and preparing it to present to Grafana.

	:param token: Token for InfluxDB
	:param output_data_file: File to write processed data to on disk.
	:param cache_data_file: File to write processed data, including that for incomplete days, to on disk.
	:param influxdb_address: Address of the InfluxDB server.
	"""

	token: str
	output_data_file: str
	cache_data_file: Optional[str]
	influxdb_address: str

	def __init__(
			self,
			token: str,
			output_data_file: str,
			cache_data_file: Optional[str] = None,
			influxdb_address: str = "http://localhost:8086",
			) -> None:
		self.token = token
		self.influxdb_address = influxdb_address
		self.output_data_file = output_data_file
		self.cache_data_file = cache_data_file

	@abstractmethod
	def update_data(self) -> None:
		"""
		Refresh processed data on disk.
		"""

	def get_data(self) -> Dict:  # TODO: KT,VT
		"""
		Returns the processed data from disk.
		"""

		json_datafile = PathPlus(self.cache_data_file)
		data = json_datafile.load_json()  # List
		for day in data:
			day["date"] = date.fromisoformat(day["date"])

		return data

	@abstractmethod
	def get_daily_endpoint_data(self) -> Any: ...

	@contextmanager
	def influxdb_client(self, org: str = "Home", timeout: int = 60_000, **kwargs) -> Iterator[InfluxDBClient]:
		r"""
		Context manager for a client for accessing InfluxDB.

		:param org: InfluxDB organisation.
		:param timeout: InfluxDB request timeout.
		:param \*\*kwargs: Additional keyword arguments for the ``InfluxDBClient`` class.
		"""

		with InfluxDBClient(
				url=self.influxdb_address,
				token=self.token,
				org=org,
				timeout=timeout,
				**kwargs,
				) as client:
			yield client
