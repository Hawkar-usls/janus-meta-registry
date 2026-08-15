#!/usr/bin/env python3
from __future__ import annotations

import argparse, datetime as dt, json, math
from pathlib import Path

# Frozen source inputs.
OBS_UTC=dt.datetime(1951,9,20,3,33,0)
EXPOSURE_MIN=60.0
PLATE_RA_DEG=15.0*(20+7/60+18.70/3600)
PLATE_DEC_DEG=18+21/60+53.9/3600
PALOMAR_LAT=33.3566666667
PALOMAR_LON=-116.8625
HOLLOMAN_LAT=32.86
HOLLOMAN_LON=-106.11
AEROBEE_ALT_KM=236000*0.0003048
DSS_PLATE_WIDTH_DEG=6.5
EARTH_R_KM=6371.0


def jd(x):
    y,m=x.year,x.month; day=x.day+(x.hour+x.minute/60+x.second/3600)/24
    if m<=2:y-=1;m+=12
    A=math.floor(y/100);B=2-A+math.floor(A/4)
    return math.floor(365.25*(y+4716))+math.floor(30.6001*(m+1))+day+B-1524.5

def altaz(ra,dec,when,lat,lon):
    J=jd(when);T=(J-2451545.0)/36525
    gmst=(280.46061837+360.98564736629*(J-2451545.0)+0.000387933*T*T-T*T*T/38710000)%360
    lst=(gmst+lon)%360;H=math.radians((lst-ra+540)%360-180);de=math.radians(dec);la=math.radians(lat)
    alt=math.asin(math.sin(de)*math.sin(la)+math.cos(de)*math.cos(la)*math.cos(H))
    y=-math.sin(H)*math.cos(de);x=math.sin(de)*math.cos(la)-math.cos(de)*math.sin(la)*math.cos(H)
    az=math.atan2(y,x)% (2*math.pi)
    return math.degrees(alt),math.degrees(az),lst

def greatcircle(lat1,lon1,lat2,lon2):
    a,b,c,d=map(math.radians,[lat1,lon1,lat2,lon2]);dl=d-b
    central=math.acos(max(-1,min(1,math.sin(a)*math.sin(c)+math.cos(a)*math.cos(c)*math.cos(dl))))
    bearing=math.atan2(math.sin(dl)*math.cos(c),math.cos(a)*math.sin(c)-math.sin(a)*math.cos(c)*math.cos(dl))%(2*math.pi)
    return central,math.degrees(bearing)

def elev_to_altitude(central,h):
    radial=(EARTH_R_KM+h)*math.cos(central)-EARTH_R_KM
    tang=(EARTH_R_KM+h)*math.sin(central)
    return math.degrees(math.atan2(radial,tang))

def sep(alt1,az1,alt2,az2):
    a,b=map(math.radians,[alt1,alt2]);A,B=map(math.radians,[az1,az2])
    q=math.sin(a)*math.sin(b)+math.cos(a)*math.cos(b)*math.cos(A-B)
    return math.degrees(math.acos(max(-1,min(1,q))))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.parent.mkdir(parents=True,exist_ok=True)
    palt,paz,lst=altaz(PLATE_RA_DEG,PLATE_DEC_DEG,OBS_UTC,PALOMAR_LAT,PALOMAR_LON)
    central,bearing=greatcircle(PALOMAR_LAT,PALOMAR_LON,HOLLOMAN_LAT,HOLLOMAN_LON)
    rocket_alt=elev_to_altitude(central,AEROBEE_ALT_KM)
    angular_sep=sep(palt,paz,rocket_alt,bearing)
    halfdiag=math.sqrt(2)*(DSS_PLATE_WIDTH_DEG/2)
    # Deliberately generous envelope around the launch-site/high-altitude column.
    vals=[]
    for az in [80+i*.25 for i in range(81)]:
      for alt in [-5+i*.25 for i in range(61)]: vals.append(sep(palt,paz,alt,az))
    conservative_min=min(vals)
    result={
      'artifact_id':'JANUS-PALOMAR-JPFM-4A-XE454-HOLLOMAN-GEOMETRY-CERTIFICATE-v1.0','date':'2026-08-15','status':'DETERMINISTIC_GEOMETRY_EXECUTED',
      'inputs':{
        'xe454_start_ut':OBS_UTC.isoformat()+'Z','xe454_exposure_minutes':EXPOSURE_MIN,'plate_center_ra_deg':PLATE_RA_DEG,'plate_center_dec_deg':PLATE_DEC_DEG,
        'palomar_lat_lon_deg':[PALOMAR_LAT,PALOMAR_LON],'holloman_lat_lon_deg':[HOLLOMAN_LAT,HOLLOMAN_LON],
        'holloman_coordinate_authority':'US National Weather Service point forecast ~32.86N 106.11W',
        'aerobee_documented_altitude_km':AEROBEE_ALT_KM,'dss_plate_width_deg':DSS_PLATE_WIDTH_DEG
      },
      'calculation':{
        'plate_center_alt_deg_at_start_ut':palt,'plate_center_az_deg_at_start_ut':paz,'local_sidereal_time_deg':lst,
        'palomar_holloman_surface_distance_km':central*EARTH_R_KM,'holloman_initial_bearing_deg_from_palomar':bearing,
        'line_of_sight_elevation_to_point_236000ft_above_holloman_deg_spherical_earth':rocket_alt,
        'angular_separation_plate_center_vs_holloman_236000ft_column_deg':angular_sep,
        'plate_half_diagonal_deg_using_6p5deg_square':halfdiag,
        'conservative_envelope':{'az_deg':[80,100],'alt_deg':[-5,10],'minimum_angular_separation_from_plate_center_deg':conservative_min}
      },
      'interpretation':{
        'direct_launch_site_high_altitude_column_inside_xe454_field':False,
        'margin_vs_plate_half_diagonal_deg':conservative_min-halfdiag,
        'result':'SPATIAL_REJECTION_FOR_DIRECT_HOLLOMAN_COLUMN_CONTAMINATION',
        'boundary':'No detailed Aerobee trajectory/launch time was recovered; this certificate rejects the launch-site/high-altitude-column geometry, not every conceivable distant trajectory or secondary phenomenon.'
      },
      'current_authority_changed':False,'claim_ceiling':'GEOMETRIC_DIRECT_COLUMN_REJECTION_ONLY__NO_GLOBAL_ROCKET_EXPLANATION'
    }
    a.out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
