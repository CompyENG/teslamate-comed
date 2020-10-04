#!/usr/bin/env python
import os
import logging
import sys
import time
import datetime
from typing import List
from dataclasses import dataclass
import pytz
import pprint
import requests
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.orm import Session
from sqlalchemy import create_engine


POSTGRES_USER = os.environ.get("POSTGRES_USER", "teslamate")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "secret")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "teslamate")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "database")

FIXED_COSTS = os.environ.get("FIXED_COSTS")
if FIXED_COSTS is None:
    FIXED_COSTS = 0.00830 + 0.00087 + 0.03598 + 0.00122 + 0.00038 + 0.00189 + 0.00195 + 0.00132
else:
    FIXED_COSTS = float(FIXED_COSTS)

HOME_LOCATION_ID = os.environ.get("HOME_LOCATION_ID")
if HOME_LOCATION_ID is None:
    HOME_LOCATION_ID = 1
else:
    HOME_LOCATION_ID = int(HOME_LOCATION_ID)

TZ = os.environ.get("TZ", "America/Chicago")


@dataclass
class ChargeDataPoint:
    date: datetime.datetime
    voltage: float
    current: float
    price_per_kWh: float

    def get_power_kW(self):
        return (self.voltage * self.current) / 1000.0

    def get_price_per_hour(self):
        return self.get_power_kW() * self.price_per_kWh


def interpolate_points(prices, charge_data):
    result: List[ChargeDataPoint] = []

    price_index = 0
    while prices[price_index+1]["date"] < charge_data[0].date:
        price_index += 1

    charge_index = 0

    # power_for_slice = charge_data[previous_point_index].charger_voltage * charge_data[previous_point_index].charger_actual_current / 1000.0

    while charge_index < (len(charge_data)-1):
        this_date = charge_data[charge_index].date
        this_voltage = float(charge_data[charge_index].charger_voltage)
        this_current = float(charge_data[charge_index].charger_actual_current)

        result.append(ChargeDataPoint(
            this_date,
            this_voltage,
            this_current,
            prices[price_index]["price"]
        ))

        if prices[price_index+1]["date"] < charge_data[charge_index+1].date:
            # Price update before next data point
            next_voltage = float(charge_data[charge_index+1].charger_voltage)
            next_current = float(charge_data[charge_index+1].charger_actual_current)
            next_date = charge_data[charge_index+1].date
            price_date = prices[price_index+1]["date"]

            voltage_slope = (next_voltage - this_voltage) / ((next_date - this_date) / datetime.timedelta(milliseconds=1))
            current_slope = (next_current - this_current) / ((next_date - this_date) / datetime.timedelta(milliseconds=1))

            next_voltage = this_voltage + voltage_slope*((price_date - this_date) / datetime.timedelta(milliseconds=1))
            next_current = this_current + current_slope*((price_date - this_date) / datetime.timedelta(milliseconds=1))

            result.append(ChargeDataPoint(
                price_date,
                next_voltage,
                next_current,
                prices[price_index+1]["price"]
            ))

            price_index += 1

        charge_index += 1

    return result


logging.basicConfig(level=logging.WARN)


try:
    while True:
        Base = automap_base()

        engine = create_engine(f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}/{POSTGRES_DB}", echo=False)

        Base.prepare(engine, reflect=True)

        Charges = Base.classes.charges
        ChargingProcesses = Base.classes.charging_processes

        session = Session(engine)

        comed_time = pytz.timezone(TZ)

        one_hour_ago = datetime.datetime.now() - datetime.timedelta(hours=1)
        processes = session.query(ChargingProcesses).filter(
            ChargingProcesses.end_date != None,
            ChargingProcesses.geofence_id == HOME_LOCATION_ID,
            ChargingProcesses.end_date < one_hour_ago,
            ChargingProcesses.cost == None
        )

        for first_process in processes:
            # Then, look in Charges for all details between start date and end date
            charge_data = session.query(Charges).filter(Charges.date >= first_process.start_date, Charges.date <= first_process.end_date).all()

            comed_data_start = first_process.start_date - datetime.timedelta(minutes=5)
            comed_data_end = first_process.end_date + datetime.timedelta(minutes=5)

            comed_url = "https://hourlypricing.comed.com/api?type=5minutefeed&datestart={0:%Y%m%d%H%M}&dateend={1:%Y%m%d%H%M}".format(
                comed_data_start.astimezone(comed_time),
                comed_data_end.astimezone(comed_time)
            )
            comed_data = requests.get(comed_url).json()

            comed_data.sort(key=lambda x: int(x['millisUTC']))

            prices = [ { "date": datetime.datetime.fromtimestamp(float(x['millisUTC']) / 1000), "price": float(x['price']) / 100 } for x in comed_data ]

            total_price = 0
            total_power = 0

            points = interpolate_points(prices, charge_data)
            point_index = 1
            for point_l, point_r in zip(points, points[1:]):
                cost_l = point_l.get_price_per_hour()
                cost_r = point_r.get_price_per_hour()

                power_l = point_l.get_power_kW()
                power_r = point_r.get_power_kW()

                time_delta_hours = (point_r.date - point_l.date) / datetime.timedelta(hours=1)

                slice_cost = ((cost_l + cost_r) / 2) * time_delta_hours
                total_price += slice_cost

                slice_power = ((power_l + power_r) / 2) * time_delta_hours
                total_power += slice_power

            total_price += FIXED_COSTS * total_power

            print(f"ID: {first_process.id}")
            print(f"Total price: {total_price}")
            print(f"Total power: {total_power} kWh")
            print(f"Average price per kWh: {sum([float(x['price']) / 100 for x in comed_data]) / len(comed_data)}")
            print(f"Average price per kWh including fixed costs: {total_price / total_power}")
            print(f"Min: {min(float(x['price']) for x in comed_data)}, Max: {max(float(x['price']) for x in comed_data)}")
            print(comed_url)
            print("------")
            print("")

            first_process.cost = total_price

        print(session.dirty)
        session.commit()

        with open("/tmp/teslamate-comed-last-update", "w") as f:
            now = datetime.datetime.utcnow()
            f.write(now.isoformat())

        time.sleep(datetime.timedelta(hours=1).total_seconds())

except KeyboardInterrupt:
    print("Exiting due to KeyboardInterrupt")
except:
    logging.exception("Unknown exception during execution")
