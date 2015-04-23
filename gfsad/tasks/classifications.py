from gfsad import celery
from gfsad.models import db, Image
from flask import current_app
import StringIO
import boto
from boto.s3.key import Key
import datetime
import gzip
import json
from gfsad.utils.s3 import upload_file_to_s3


@celery.task
def compute_image_classification_statistics(image_id):
    image = Image.query.get(image_id)

    classification_count = [0 for i in range(0, 10)]

    for record in image.classifications:
        classification_count[record.classification] += 1

    image.classifications_majority_class = 0
    for i, count in enumerate(classification_count):
        if count > classification_count[image.classifications_majority_class]:
            image.classifications_majority_class = i

    image.classifications_count = sum(classification_count)
    image.classifications_majority_agreement = 100 * classification_count[
        image.classifications_majority_class] / image.classifications_count

    image.classifications_count = sum(classification_count)

    db.session.commit()


@celery.task(rate_limit="6/h")
def build_classifications_result():
    LICENSE = """This data is made available under the Open Database License:
    http://opendatacommons.org/licenses/odbl/1.0/. Any rights in individual
    contents of the database are licensed under the Database Contents License:
    http://opendatacommons.org/licenses/dbcl/1.0/"""

    ATTRIBUTION = 'Global Food Security Analysis-Support Data at 30m, http://www.croplands.org'
    classes = [
            {'id': 0, 'order': 0, 'label': 'Unknown', 'description': 'Not cropland is...'},
            {'id': 1, 'order': 1, 'label': 'Cropland', 'description': 'Cropland is...'},
            {'id': 2, 'order': 2, 'label': 'Forest', 'description': 'Forest is ...'},
            {'id': 3, 'order': 3, 'label': 'Grassland', 'description': 'Grassland is ...'},
            {'id': 4, 'order': 5, 'label': 'Barren', 'description': 'Barrenland is ...'},
            {'id': 5, 'order': 7, 'label': 'Urban/Builtup', 'description': 'Urban is ...'},
            {'id': 6, 'order': 4, 'label': 'Shrub', 'description': 'Shrub is ...'},
            {'id': 7, 'order': 6, 'label': 'Water', 'description': 'Water is ...'}
        ]
    cmd = """
          SELECT
          location.lat,
          location.lon,
          image.classifications_count,
          image.classifications_majority_class,
          image.classifications_majority_agreement,
          image.date_acquired,
          image.date_acquired_earliest,
          image.date_acquired_latest

          FROM image
          JOIN location on image.location_id = location.id
          WHERE classifications_count > 0
          """

    result = db.engine.execute(cmd)
    columns = result.keys()
    records = [
        [
            row['lat'], row['lon'],
            row['classifications_count'],
            row['classifications_majority_class'],
            row['classifications_majority_agreement'],
            row['date_acquired'].strftime("%Y-%m-%d"),
            row['date_acquired_earliest'].strftime("%Y-%m-%d"),
            row['date_acquired_latest'].strftime("%Y-%m-%d"),
        ] for row in result
    ]

    print "Building json with %d classifications" % len(records)


    # Connect to S3
    s3 = boto.connect_s3(current_app.config['AWS_ACCESS_KEY_ID'],
                         current_app.config['AWS_SECRET_ACCESS_KEY'])

    # Get bucket
    bucket = s3.get_bucket(current_app.config['AWS_S3_BUCKET'])

    if current_app.testing:
        key = 'test/json/classifications.test.json'
        key_csv = 'test/json/classifications.test.csv'
    else:
        key = 'public/json/classifications.json'
        key_csv = 'public/json/classifications.csv'

    content = {
        'num_results': len(records),
        'meta': {
            'created': datetime.datetime.utcnow().isoformat(),
            'columns': columns,
            'class_mapping': [c['label'] for c in classes],
            'license': LICENSE,
            'attribution': ATTRIBUTION
        },
        'objects': records
    }

    upload_file_to_s3(json.dumps(content), key, 'application/javascript')
    # # fake a file for gzip
    # out = StringIO.StringIO()
    # out_csv = StringIO.StringIO()
    #
    # k = Key(bucket)
    #
    #
    # k.key = key
    #
    # k.set_metadata('content-type', 'application/javascript')
    # k.set_metadata('cache-control', 'max-age=3000')
    # k.set_metadata('content-encoding', 'gzip')
    #
    # with gzip.GzipFile(fileobj=out, mode="w") as outfile:
    #     outfile.write(json.dumps(content))
    #
    # k.set_contents_from_string(out.getvalue())
    # k.make_public()
    #
