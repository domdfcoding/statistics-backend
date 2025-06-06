#!/usr/bin/env python3
#
#  energy_utils.py
"""
Utilities for processing electricity consumption data.
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
import itertools
import operator
import os
from calendar import monthrange
from datetime import date, timedelta
from typing import Dict, List

# 3rd party
from domdf_python_tools.paths import PathPlus
from influxdb_client import InfluxDBClient

__all__ = ["update_energy_data"]


class EnergyBackend:
	token: str
	voltage_source: str
	influxdb_address: str
	output_data_file: str
	cache_data_file: str

	def __init__(
			self,
			token: str,
			voltage_source: str,
			influxdb_address: str = "http://localhost:8086",
			output_data_file: str = "daily_energy.json",
			cache_data_file: str = "daily_energy_cache.json",
			) -> None:
		self.token = token
		self.voltage_source = voltage_source
		self.influxdb_address = influxdb_address
		self.output_data_file = output_data_file
		self.cache_data_file = cache_data_file

	def update_data(self) -> None:

		json_datafile = PathPlus(self.output_data_file)
		if json_datafile.is_file():
			consumption_data = json_datafile.load_json()  # List
			for day in consumption_data:
				day["date"] = date.fromisoformat(day["date"])
			latest_date = consumption_data[-1]["date"]

		else:
			consumption_data = []
			latest_date = date(year=2022, month=8, day=1)

		today = date.today()

		with InfluxDBClient(
				url=self.influxdb_address,
				token=self.token,
				org="Home",
				timeout=60_000,
				) as client:

			query = f"""
		import "interpolate"
		import "date"

		current = from(bucket: "telegraf")
		|> range(start: date.truncate(t: {(latest_date+timedelta(days=1)).isoformat()}T00:00:00Z, unit: 1d), stop: now())
		|> filter(fn: (r) => r["topic"] == "CT_CLAMP/tele/SENSOR")
		|> filter(fn: (r) => r["_field"] == "Current")
		|> aggregateWindow(every: 1h, fn: mean)

		voltage = from(bucket: "telegraf")
		|> range(start: date.truncate(t: {(latest_date+timedelta(days=1)).isoformat()}T00:00:00Z, unit: 1d), stop: now())
		|> filter(fn: (r) => r["topic"] == "{self.voltage_source}/tele/SENSOR")
		|> filter(fn: (r) => r["_field"] == "ENERGY_Voltage")
		|> aggregateWindow(every: 1h, fn: mean)

		join(
			tables: {{voltage:voltage, current:current}},
			on: ["_time", "_stop", "_start", "host"],
		)
		|> map(fn: (r) => ({{ r with _value_power: r._value_current * r._value_voltage }}))
		|> map(fn: (r) => ({{ _time: r._time, "1": r._value_power, "2": r._value_current, "3": r._value_voltage}}))
		|> rename(columns: {{ "1": "_value", "2": "Current (A)", "3": "Voltage (V)"}})
		|> truncateTimeColumn(unit: 1h)
		|> aggregateWindow(every: 1h, fn: mean, createEmpty: false, timeSrc: "_start")
		|> aggregateWindow(every: 1d, fn: sum, createEmpty: false, timeSrc: "_start")
		|> yield(name: "sum")
		"""

			tables = client.query_api().query(query)

			all_values = [x.values.get("_value") for x in tables[0]]
			period_start_times = [x.values.get("_time") for x in tables[0]]

			for rainfall, day in zip(all_values, period_start_times):
				consumption_data.append({"date": day.date(), "consumption": rainfall})

		output_data = []
		save_data = []
		for daily_data in consumption_data:
			if daily_data["consumption"] is None:
				continue
			prepared_data = {"date": daily_data["date"].isoformat(), "consumption": daily_data["consumption"]}
			# prepared_data = {"date": daily_data["date"], "consumption": daily_data["consumption"]}
			output_data.append(prepared_data)
			if daily_data["date"] != today:
				save_data.append(prepared_data)

		PathPlus(self.cache_data_file).dump_json(output_data)
		json_datafile.dump_json(save_data)

	def get_data(self) -> Dict:  # TODO: KT,VT

		json_datafile = PathPlus(self.cache_data_file)
		energy_data = json_datafile.load_json()  # List
		for day in energy_data:
			day["date"] = date.fromisoformat(day["date"])

		return energy_data

	def get_daily_endpoint_data(self) -> List:  # TODO: KT
		output_data = []
		for daily_data in self.get_data():
			prepared_data = {"date": daily_data["date"], "consumption": daily_data["consumption"]}
			output_data.append(prepared_data)

		return list(reversed(output_data))

	def get_monthly_endpoint_data(self) -> List:  # TODO: KT
		monthly_energy = {}
		today = date.today()

		for (year, month), daily_data in itertools.groupby(self.get_data(), lambda x: (x["date"].year, x["date"].month)):
			daily_energy_list = list(map(operator.itemgetter("consumption"), daily_data))
			days_in_month = monthrange(year, month)[1]

			if month == today.month:
				days_in_month = today.day

			average_energy = sum(daily_energy_list) / days_in_month
			# print(year, month, average_energy)

			monthly_energy[f" {month:02d}/{year}"] = {
					"total": sum(daily_energy_list),
					"average": average_energy,
					"complete_month": month != today.month or year != today.year,
					}

		current_month_key = f" {today.month:02d}/{today.year}"
		if current_month_key in monthly_energy:
			monthly_energy["current"] = monthly_energy[current_month_key]
		else:
			# No rain this month!
			monthly_energy["current"] = {
					"total": 0,
					"average": 0,
					"complete_month": False,
					}

		return monthly_energy
