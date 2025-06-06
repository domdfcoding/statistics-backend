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
from datetime import date
from typing import Any, Dict

# 3rd party
from domdf_python_tools.paths import PathPlus

__all__ = ["Backend"]


class Backend(ABC):
	token: str
	output_data_file: str
	influxdb_address: str

	def __init__(
			self,
			token: str,
			output_data_file: str,
			influxdb_address: str = "http://localhost:8086",
			) -> None:
		self.token = token
		self.influxdb_address = influxdb_address
		self.output_data_file = output_data_file

	@abstractmethod
	def update_data(self) -> None: ...

	def get_data(self) -> Dict:  # TODO: KT,VT

		json_datafile = PathPlus(self.cache_data_file)
		data = json_datafile.load_json()  # List
		for day in data:
			day["date"] = date.fromisoformat(day["date"])

		return data

	@abstractmethod
	def get_daily_endpoint_data(self) -> Any: ...
