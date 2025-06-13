import logging
import io
from lxml import etree

from netexio.database import Database
from netexio.dbaccess import setup_database, open_netex_file, insert_database
from netexio.pickleserializer import MyPickleSerializer
from utils.utils import get_interesting_classes
from utils.aux_logging import *
from netexio.dbaccess import check_referencing


def preprocess_xml_file(file_obj: io.IOBase) -> io.BytesIO:
    """
    Preprocesses an XML file to add missing nameOfRefClass attributes
    to *ObjectRef elements.
    """
    content = file_obj.read()
    if not content:
        return io.BytesIO(b"")

    try:
        # Using a BytesIO object to parse from memory
        parser = etree.XMLParser(recover=True)  # recover from errors
        tree = etree.parse(io.BytesIO(content), parser)
        root = tree.getroot()

        fix_count = 0
        for element in root.iter():
            tag = etree.QName(element.tag)
            if tag.localname.endswith('ObjectRef'):
                if 'nameOfRefClass' not in element.attrib:
                    ref = element.get('ref')
                    if ref:
                        parts = ref.split(':')
                        if len(parts) > 1:
                            name_of_ref_class = parts[1]
                            element.set('nameOfRefClass', name_of_ref_class)
                            fix_count += 1

        if fix_count > 0:
            logging.info(f"Added nameOfRefClass to {fix_count} elements.")

        modified_xml_bytes = etree.tostring(tree, xml_declaration=True, encoding='UTF-8')
        return io.BytesIO(modified_xml_bytes)
    except etree.XMLSyntaxError as e:
        logging.warning(f"Failed to parse XML, returning empty content. Error: {e}")
        return io.BytesIO(b"")


def main(filenames: list[str], database: str, clean_database: bool = True) -> None:
    # if filenames is not a list of str  => error
    if not (isinstance(filenames, list) and all(isinstance(item, str) for item in filenames)):
        log_all(logging.ERROR, f'filenames parameter must be a [] of file names.')
        log_flush()
        exit(1)

    with Database(database, MyPickleSerializer(compression=True), readonly=False,
                  logger=logging.getLogger("script_runner")) as db:
        classes = get_interesting_classes()

        if clean_database:
            print("Is cleaned!")
            setup_database(db, classes, clean_database)

        for filename in filenames:
            logging.info(f"--- Processing file: {filename} ---")
            for sub_file in open_netex_file(filename):
                logging.info("Preprocessing XML sub-file...")
                processed_file = preprocess_xml_file(sub_file)
                if processed_file.getbuffer().nbytes > 0:
                    logging.info("Inserting preprocessed file into database...")
                    insert_database(db, classes, processed_file)
                else:
                    logging.info("Skipping empty preprocessed file.")
            logging.info(f"--- Finished processing file: {filename} ---")

        db.block_until_done()

        # check_referencing(db)


if __name__ == '__main__':
    import argparse

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    argument_parser = argparse.ArgumentParser(description='Import any NeTEx source into lmdb')
    argument_parser.add_argument('netex', nargs='+', default=[], help='NeTEx files')
    argument_parser.add_argument('database', type=str, help='The lmdb to be overwritten with the NeTEx context')
    argument_parser.add_argument('--clean_database', action="store_true", help='Clean the current file', default=True)
    args = argument_parser.parse_args()

    main(args.netex, args.database, args.clean_database)
