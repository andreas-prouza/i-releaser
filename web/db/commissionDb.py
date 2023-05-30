from array import array
import logging
from multiprocessing.dummy import Array
import pyodbc
from etc import db_config

class CommissionDb: 



    def __init__(self):

        dbHost = db_config.DATABASES['IBM_I']['HOST']
        dbUsername = db_config.DATABASES['IBM_I']['USER'] 
        dbPassword = db_config.DATABASES['IBM_I']['PASSWORD']
        
        #self.cnxn = pyodbc.connect('DSN=*LOCAL')
        logging.debug(f"DRIVER={{IBM i Access ODBC Driver}};SYSTEM={dbHost};UID={dbUsername};PWD=xxx")
        self.cnxn = pyodbc.connect(f"DRIVER={{IBM i Access ODBC Driver}};SYSTEM={dbHost};UID={dbUsername};PWD={dbPassword};Naming=1;DefaultLibraries=WWSDTARIST WWSLIBRIST GRTOOL")
        self.db = self.cnxn.cursor()
        self.last_error = None



    def get_value(self):
        self.db.execute("""Values 1""")
        return self.get_with_column_names(self.db)



    #########################################################
    # Just to appand column name to each column in each row
    #########################################################
    def get_with_column_names(self, cursor):
        column_names = [column[0] for column in cursor.description]

        rows = cursor.fetchall()
        newData = []
        for row in rows:
            tmprow = {}
            for k, v in zip(column_names, row):
                tmprow[k] = v
            newData.append(tmprow)

        return newData