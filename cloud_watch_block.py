import re
import logging
from enum import Enum
import datetime
from nio.common.discovery import Discoverable, DiscoverableType
from nio.common.block.base import Block
from nio.common.signal.base import Signal
from nio.metadata.properties import ObjectProperty, PropertyHolder, \
    IntProperty, StringProperty, SelectProperty
from nio.metadata.properties.version import VersionProperty
from nio.modules.threading import Lock

from boto.ec2.cloudwatch import connect_to_region


class AWSRegion(Enum):
    us_east_1 = 0
    us_west_2 = 1
    eu_west_1 = 2


class MetricStatistics(Enum):
    Average = 0
    Sum = 1
    SampleCount = 2
    Maximum = 3
    Minimum = 4


class AWSCreds(PropertyHolder):
    access_key = StringProperty(title="Access Key",
                                default="[[AMAZON_ACCESS_KEY_ID]]")
    access_secret = StringProperty(title="Access Secret",
                                   default="[[AMAZON_SECRET_ACCESS_KEY]]")
    region = SelectProperty(
        AWSRegion, default=AWSRegion.us_east_1, title="AWS Region")


@Discoverable(DiscoverableType.block)
class CloudWatch(Block):

    creds = ObjectProperty(AWSCreds, title="AWS Credentials")
    metric = StringProperty(
        title="Metric to Monitor", default="CPUCreditBalance")
    lookback_mins = IntProperty(title="Lookback Minutes", default=5)
    result_period = IntProperty(title="Result Period Minutes", default=5)
    statistic = SelectProperty(MetricStatistics, title="Statistic Type",
                               default=MetricStatistics.Average)
    version = VersionProperty('0.0.1')

    def __init__(self):
        super().__init__()
        self._conn = None
        self._metrics = []
        self._metrics_lock = Lock()

    def configure(self, context):
        super().configure(context)
        # Set boto's log level to be the same as ours
        logging.getLogger('boto').setLevel(self._logger.logger.level)
        try:
            self._connect()
            self._sync_metrics()
        except:
            self._logger.exception(
                "Unable to connect to region - make sure your "
                "credentials are correct")
            raise

    def _connect(self):
        """ Create a connection to AWS using our credentials """
        region_name = re.sub('_', '-', self.creds.region.name)
        self._logger.debug("Connecting to region {}...".format(region_name))
        self._conn = connect_to_region(
            region_name,
            aws_access_key_id=self.creds.access_key,
            aws_secret_access_key=self.creds.access_secret)
        self._logger.debug("Connection complete")

    def _sync_metrics(self):
        """ Makes a request to CloudWatch and stores valid metrics

        This method takes the configured metric name and obtains all of the
        valid metrics that match that metric name. Metric objects contain
        namespace, dimensions, and possibly some other important information
        for querying later.

        Returns:
            None: saves the metics in the self._metrics list instead
        """
        with self._metrics_lock:
            self._logger.debug(
                "Syncing valid metrics for {} from EC2".format(self.metric))
            metrics_res = self._conn.list_metrics(metric_name=self.metric)
            self._metrics[:] = metrics_res
            self._logger.debug("{} metrics loaded".format(len(self._metrics)))

    def process_signals(self, signals, input_id='default'):
        # Only make one request per batch of signals
        # It currently doesn't make sense to make multiple requests at once
        with self._metrics_lock:
            results = self._execute_requests()
        if results:
            self.notify_signals(results)

    def _execute_requests(self):
        """ Go through the saved metrics and capture their values.

        This method should be called inside of the metrics Lock
        """
        signals_out = []
        for metric in self._metrics:
            # Get the list of metrics
            try:
                self._logger.debug("Getting value for {}".format(metric))
                metric_vals = self._get_metric_value(metric)
                if len(metric_vals):
                    # We only care about the first metric - this is the newest
                    val = metric_vals[0][self.statistic.name]
                    self._logger.debug("Metric's value was {}".format(val))
                    signals_out.append(Signal({
                        'dimensions': metric.dimensions,
                        'value': val
                    }))
                else:
                    self._logger.info(
                        'Metric {} did not return any metric value'.format(
                            metric))
            except:
                # Unable to get the value for this metric, ignore this one
                self._logger.exception(
                    'Unable to get metric for {}'.format(metric))

        return signals_out

    def _get_metric_value(self, metric):
        """ Gets the value(s) of the saved metric object """
        # Prepare some variables
        end_time = datetime.datetime.utcnow()
        start_time = end_time - datetime.timedelta(minutes=self.lookback_mins)

        # Make the request
        results = self._conn.get_metric_statistics(
            period=(self.result_period * 60),
            start_time=start_time,
            end_time=end_time,
            metric_name=metric.name,
            namespace=metric.namespace,
            statistics=self.statistic.name,
            dimensions=metric.dimensions)

        return results
