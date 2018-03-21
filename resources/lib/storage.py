# -*- coding: utf-8 -*-

import sqlite3 as db


class SeriesDatabase:

    def __init__(self, db_filename, logger):
        self.logger = logger
        self.c = db.connect(database=db_filename)
        self.cu = self.c.cursor()

    def __del__(self):
        self.c.close()

    def add_to_db(self, item_to_add, info_to_add):
        info_to_add = info_to_add.replace("'", "XXCC").replace('"', "XXDD")
        tor_id = "n" + item_to_add.replace('/', "_").replace('-', "_")
        item_length = str(len(info_to_add))
        failed_to_create = False
        try:
            self.cu.execute("CREATE TABLE " + tor_id + " (db_item VARCHAR(" + item_length + "), i VARCHAR(1));")
            self.c.commit()
        except Exception, err:
            failed_to_create = True
            self.logger.log.info("Database error, cannot add %s, insert instead" % str(err))

        if not failed_to_create:
            self.cu.execute('INSERT INTO ' + tor_id + ' (db_item, i) VALUES ("' + info_to_add + '", "1");')
            self.c.commit()

    def get_inf_db(self, item_to_get):
        table_id = "n" + item_to_get.replace('/', "_").replace('-', "_")
        self.cu.execute("SELECT db_item FROM " + table_id + ";")
        self.c.commit()
        l_info = self.cu.fetchall()
        info = l_info[0][0].replace("XXCC", "'").replace("XXDD", '"')
        return info

    def rem_inf_db(self, item_to_remove):
        table_id = "n" + item_to_remove.replace('/', "_").replace('-', "_")
        try:
            self.cu.execute("DROP TABLE " + table_id + ";")
            self.c.commit()
        except Exception, err:
            self.logger.log.info("Database error, cannot delete %s" % str(err))
