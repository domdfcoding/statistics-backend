#!/usr/bin/env python3
#
#  temperature_utils.py
"""
Utilities for processing temperature data.
"""
#
#  Copyright © 2023 Dominic Davis-Foster <dominic@davis-foster.co.uk>
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
import os
from datetime import date, datetime, timedelta
from itertools import groupby
from statistics import mean
from typing import Dict

# 3rd party
from astral import LocationInfo
from astral.sun import sun
from domdf_python_tools.paths import PathPlus
from influxdb_client import InfluxDBClient

__all__ = ["TemperatureBackend"]


class TemperatureBackend:
	token: str
	temperature_source: str
	influxdb_address: str
	output_data_file: str
	cache_data_file: str

	def __init__(
			self,
			token: str,
			temperature_source: str,
			influxdb_address: str = "http://localhost:8086",
			output_data_file: str = "daily_temperatures.json",
			) -> None:
		self.token = token
		self.temperature_source = temperature_source
		self.influxdb_address = influxdb_address
		self.output_data_file = output_data_file

	def update_data(self) -> None:

		latest_date = date(year=2022, month=7, day=1)

		json_datafile = PathPlus(self.output_data_file)
		if json_datafile.is_file():
			temperature_data = json_datafile.load_json()  # List
			for day, daily_data in temperature_data.items():
				temperature_data[day]["sunset"] = datetime.fromisoformat(daily_data["sunset"])
				temperature_data[day]["sunrise"] = datetime.fromisoformat(daily_data["sunrise"])
				latest_date = max(date.fromisoformat(day), latest_date)

		else:
			temperature_data = {}

		today = date.today().isoformat()

		city = LocationInfo("Stoke-on-Trent", "England", "Europe/London", 53.0342901, -2.1630222)

		with InfluxDBClient(
				url=self.influxdb_address,
				token=self.token,
				org="Home",
				timeout=60_000,
				) as client:

			query = f"""
		import "math"
		import "date"

		from(bucket: "telegraf")
		|> range(start: date.truncate(t: {(latest_date+timedelta(days=1)).isoformat()}T00:00:00Z, unit: 1d), stop: now())
		|> filter(fn: (r) => r["topic"] == "{self.temperature_source}/tele/SENSOR")
		|> filter(fn: (r) => r["_field"] == "BMP280_Temperature" or r["_field"] == "BME280_Temperature")
		|> drop(columns: ["host"])
		|> group()
		"""

			tables = client.query_api().query(query)

			data = []

			for x in tables[0]:
				data.append((x.values.get("_time"), x.values.get("_value")))

		for day, daily_data in groupby(data, lambda d: d[0].date()):
			s = sun(city.observer, date=day)
			sunrise = s["sunrise"]
			sunset = s["sunset"]

			# print(day)

			# print("  Sunrise:", sunrise)
			# print("  Sunset:", sunset)
			nighttime = []
			daytime = []
			for datapoint in daily_data:
				if datapoint[1] < -140:
					continue
				if datapoint[0] < sunrise:
					nighttime.append(datapoint[1])
				elif sunrise <= datapoint[0] <= sunset:
					daytime.append(datapoint[1])
				elif datapoint[0] > sunset:
					nighttime.append(datapoint[1])

			temperature_data[day.isoformat()] = {
					# "date": day,
					"sunrise": sunrise,
					"sunset": sunset,
					"daytime": daytime,
					"nighttime": nighttime,
					}

			# all_day = daytime+nighttime
			# print("  Average (min, max):", mean(all_day), min(all_day), max(all_day))
			# print("  Daytime (min, max):", mean(daytime), min(daytime), max(daytime))
			# print("  Nighttime (min, max):", mean(nighttime), min(nighttime), max(nighttime))

		output_data = {}
		for day, daily_data in temperature_data.items():
			if day == today:
				continue
			for_json_data = daily_data.copy()
			# for_json_data["date"] = for_json_data["date"].isoformat()
			for_json_data["sunrise"] = for_json_data["sunrise"].isoformat()
			for_json_data["sunset"] = for_json_data["sunset"].isoformat()
			output_data[day] = for_json_data

		json_datafile.dump_json(output_data)

	def get_data(self) -> Dict:  # TODO: KT,VT
		json_datafile = PathPlus(self.output_data_file)
		return json_datafile.load_json()  # List

	def get_daily_endpoint_data(self) -> Dict:  # TODO: KT,VT

		min_max_data = {}

		for day, daily_data in self.get_data().items():

			nighttime = daily_data["nighttime"]
			daytime = daily_data["daytime"]
			all_day = daytime + nighttime

			min_max_data[day] = {
					"sunrise": daily_data["sunrise"],
					"sunset": daily_data["sunset"],
					"average": mean(all_day),
					"min": min(all_day),
					"max": max(all_day),
					"day_average": mean(daytime),
					"day_min": min(daytime),
					"day_max": max(daytime),
					"night_average": mean(nighttime),
					"night_min": min(nighttime),
					"night_max": max(nighttime),
					}

		return min_max_data
