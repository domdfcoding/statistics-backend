#!/usr/bin/env python3
#
#  rainfall.py
"""
Backend for processing rainfall data.
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
import itertools
import operator
from calendar import monthrange
from datetime import date, timedelta
from typing import Dict, List

# 3rd party
from domdf_python_tools.paths import PathPlus

# this package
from statistics_backend.backend import Backend

__all__ = ["RainfallBackend"]

mins_15 = timedelta(minutes=15)


class RainfallBackend(Backend):
	"""
	Backend for processing rainfall data.

	:param token: Token for InfluxDB
	:param influxdb_address: Address of the InfluxDB server.
	:param output_data_file: File to write processed data to on disk.
	:param cache_data_file:
	"""

	def __init__(
			self,
			token: str,
			influxdb_address: str = "http://localhost:8086",
			output_data_file: str = "daily_rainfall.json",
			cache_data_file: str = "daily_rainfall_cache.json",
			) -> None:
		super().__init__(
				token,
				output_data_file=output_data_file,
				cache_data_file=cache_data_file,
				influxdb_address=influxdb_address,
				)

	def update_data(self) -> None:
		"""
		Refresh processed data on disk.
		"""

		json_datafile = PathPlus(self.output_data_file)
		if json_datafile.is_file():
			rainfall_data = json_datafile.load_json()  # List
			for day in rainfall_data:
				day["date"] = date.fromisoformat(day["date"])
			latest_date = rainfall_data[-1]["date"]

		else:
			rainfall_data = []
			latest_date = date(year=2022, month=8, day=1)

		today = date.today()

		with self.influxdb_client() as client:

			query = f"""
		import "math"
		import "date"

		from(bucket: "telegraf")
		|> range(start: date.truncate(t: {(latest_date+timedelta(days=1)).isoformat()}T00:00:00Z, unit: 1d), stop: now())
		|> filter(fn: (r) => r["topic"] == "WEATHER_TEST/SENSOR")
		|> filter(fn: (r) => r["_field"] == "Rainfall")
		|> drop(columns: ["host"])
		|> truncateTimeColumn(unit: 1d)
		|> aggregateWindow(every: 1d, fn: sum, createEmpty: false, timeSrc: "_start")
		|> yield(name: "sum")
		"""

			tables = client.query_api().query(query)

			all_values = [x.values.get("_value") for x in tables[0]]
			period_start_times = [x.values.get("_time") for x in tables[0]]

			for rainfall, day in zip(all_values, period_start_times):
				if rainfall > 0.28:  # Occasionally, especially if there's a gust, the bucket can tip even if it isn't raining.
					rainfall_data.append({"date": day.date(), "rainfall_mm": rainfall})

		output_data = []
		save_data = []
		for daily_data in rainfall_data:
			prepared_data = {"date": daily_data["date"].isoformat(), "rainfall_mm": daily_data["rainfall_mm"]}
			# prepared_data = {"date": daily_data["date"], "rainfall_mm": daily_data["rainfall_mm"]}
			output_data.append(prepared_data)
			if daily_data["date"] != today:
				save_data.append(prepared_data)

		PathPlus(self.cache_data_file).dump_json(output_data)
		json_datafile.dump_json(save_data)

	def get_daily_endpoint_data(self) -> List:  # TODO: KT
		"""
		Returns processed data for the daily rainfall endpoint.
		"""

		output_data = []
		for daily_data in self.get_data():
			prepared_data = {"date": daily_data["date"], "rainfall_mm": daily_data["rainfall_mm"]}
			output_data.append(prepared_data)

		return list(reversed(output_data))

	def get_monthly_endpoint_data(self) -> Dict:  # TODO: KT,VT
		"""
		Returns processed data for the monthly rainfall endpoint.
		"""

		monthly_rainfall = {}
		today = date.today()

		for (year, month), daily_data in itertools.groupby(self.get_data(), lambda x: (x["date"].year, x["date"].month)):
			daily_rainfall_list = list(map(operator.itemgetter("rainfall_mm"), daily_data))
			days_in_month = monthrange(year, month)[1]

			if month == today.month and year == today.year:
				days_in_month = today.day

			average_rainfall = sum(daily_rainfall_list) / days_in_month
			# print(year, month, average_rainfall)

			monthly_rainfall[f" {month:02d}/{year}"] = {
					"total": sum(daily_rainfall_list),
					"days": len(daily_rainfall_list),
					"average": average_rainfall,
					"complete_month": month != today.month or year != today.year,
					}

			current_month_key = f" {today.month:02d}/{today.year}"
			if current_month_key in monthly_rainfall:
				monthly_rainfall["current"] = monthly_rainfall[current_month_key]
			else:
				# No rain this month!
				monthly_rainfall["current"] = {
						"total": 0,
						"days": 0,
						"average": 0,
						"complete_month": False,
						}

		return monthly_rainfall

	def get_yearly_endpoint_data(self) -> Dict:  # TODO: KT,VT
		"""
		Returns processed data for the annual rainfall endpoint.
		"""

		monthly_rainfall = self.get_monthly_endpoint_data()
		yearly_rainfall = {}

		today = date.today()

		for month, month_data in monthly_rainfall.items():
			if month == "current":
				continue  # TODO

			year = month.split('/')[1]

			if year not in yearly_rainfall:
				yearly_rainfall[year] = {
						"total": 0,
						"days": 0,
						"average": 0,
						"complete_year": year != str(today.year),
						}
			yearly_rainfall[year]["total"] += month_data["total"]
			yearly_rainfall[year]["days"] += month_data["days"]
			# yearly_rainfall[year]["average"] += month_data["average"]
			yearly_rainfall[year]["average"] = yearly_rainfall[year]["total"] / yearly_rainfall[year]["days"]

		current_year_key = str(today.year)
		if current_year_key in yearly_rainfall:
			yearly_rainfall["current"] = yearly_rainfall[current_year_key]
		else:
			# No rain this year!
			yearly_rainfall["current"] = {
					"total": 0,
					"days": 0,
					"average": 0,
					"complete_year": False,
					}

		return dict(yearly_rainfall)
