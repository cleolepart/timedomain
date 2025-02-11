#!/bin/bash
## This is similar to cron_test.sh but is not called with sbatch, 
## Because it runs sbatch itself
## It interacts with the sqlite3 db called 
## /global/cfs/cdirs/desi/science/td/daily-search/transients_search.db
## Blame Antonella Palmese version Jan 2021 for the ugliness of this code
### ['###' means comment by Cleo Lepart] Reworked to store unprocessed data in table (processed_daily) and available to call with iterators.py
### attaches desi.db to transients_search.db 
## 06/08/21 18:05:00 Cleo Lepart

### set -e
echo `date` Running daily time domain pipeline on `hostname`
#- Configure desi environment if needed
if [ -z "$DESI_ROOT" ]; then
    echo "Loading DESI modules"
    module use /global/common/software/desi/$NERSC_HOST/desiconda/startup/modulefiles
    echo "module load"
    module load desimodules/master
fi

tiles_path="/global/project/projectdirs/desi/spectro/redux/daily/tiles" 

run_path="/global/cscratch1/sd/akim/project/timedomain/cronjobs/" 

td_path="/global/cfs/cdirs/desi/science/td/daily-search/" 
##################
#Now double check that we have run over all new exposures. If not, we send new runs.
#The database is updated in the next lines starting where it calls python ${run_path}exposure_db.py
#That script updates the exposures table, which is later compared to the processed exposures in 
#desitrip_exposures to find unprocessed exposures. 
#desitrip_exposures is then updated with new exposures that went through the classifier in the classifier script
#ATM this only works for desitrip outputs - needs to be added to specdiff

echo "Looking for new exposures"


python ${run_path}exposure_db.py daily #creates exposures db cf. below from transients_search.db cf. /cronjobs/exposure_db.py L162 ?
query="select distinct obsdate,tileid from exposures where (tileid,obsdate) not in (select tileid,obsdate from desidiff_H_coadd_exposures);"
# query="select distinct obsdate,tileid from exposures
# where (tileid,obsdate) not in (select tileid,obsdate from desidiff_cv_coadd_exposures);"

mapfile -t -d $'\n' obsdates_tileids < <( sqlite3 ${td_path}transients_search.db "$query" )

attach="attach database '/global/cfs/cdirs/desi/science/td/db/desi.db' as desi_db;"
###unable to open database file

#sqlite3 "" <<EndOfSqlite3Commands
#ATTACH '/global/cfs/cdirs/desi/science/td/db/desi.db' AS desi_db;
#EndOfSqlite3Commands
 
    ### outside of loop?? yes, with current ON condition
    #sqlite3 ${td_path}transients_search.db "$attach" .databases;
    #sqlite3 ${td_path}transients_search.db .databases
    #attach desi



Nobsdates_tileids=${#obsdates_tileids[@]} #gets cardinality
    echo "${Nobsdates_tileids[@]}"
    
nper=1
nloop=$(((Nobsdates_tileids+nper-1)/nper))

    for ((i=0;i<$nloop;i++)); 
        do 
            subarr=("${obsdates_tileids[@]:$(($i*$nper)):$nper}")
            echo "${subarr[@]}"
        for t in ${subarr[@]}; do
                    arrt=(${t//|/ })
                    echo "${arrt[@]}"
                    #insert="INSERT INTO processed_daily(TARGETID,YYYYMMDD,TILEID,PETAL) VALUES(?,${arrt[0]},${arrt[1]},?);"
                    #echo $insert
                    #sqlite3 ${td_path}transients_search.db "$insert"
                    compare="INSERT INTO processed_daily SELECT desi.TARGETID,desi.TILEID,desi.YYYYMMDD, desi.PETAL FROM desi_db.fibermap_daily desi WHERE desi.TILEID=${arrt[1]};"
                    echo $compare
                    sqlite3 ${td_path}transients_search.db "$attach" .databases "$compare"
                    #ATTACH '/global/cfs/cdirs/desi/science/td/db/desi.db' AS desi_db;
                    
                    
        done
    done
    
    ###column implementation in processed_daily, a new table created in order to store processed targetid, tileid, obsdate data gleaned from desi.db
    ###PRAGMA table_info(processed_daily);
    ###0|TARGETID|INT|0||0
    ###1|TILEID|INT|0||0
    ###2|YYYYMMDD|INT|0||0
    ###3|PETAL|INT|0||0
    
    
   