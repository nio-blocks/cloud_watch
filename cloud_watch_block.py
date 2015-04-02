import re
import logging
from enum import Enum
import datetime
from nio.common.discovery import Discoverable, DiscoverableType
from nio.common.block.base import Block
from nio.common.signal.base import Signal
from nio.metadata.properties import ObjectProperty, PropertyHolder, \
    IntProperty, StringProperty, SelectProperty, VersionProperty
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
        self._instance_ids = []
        self._instance_ids_lock = Lock()

    def configure(self, context):
        super().configure(context)
        # Set boto's log level to be the same as ours
        logging.getLogger('boto').setLevel(self._logger.logger.level)
        self._connect()
        self._sync_instances()

    def _connect(self):
        """ Create a connection to AWS using our credentials """
        region_name = re.sub('_', '-', self.creds.region.name)
        self._logger.debug("Connecting to region {}...".format(region_name))
        self._conn = connect_to_region(
            region_name,
            aws_access_key_id=self.creds.access_key,
            aws_secret_access_key=self.creds.access_secret)
        self._logger.debug("Connection complete")

    def _sync_instances(self):
        """ Makes a request to EC2 and stores valid instance IDs.

        The Instance IDs will be instances that have the supplied metric
        available for monitoring. So non-burstable instances won't appear
        if the metric is CPUCreditBalance, e.g.

        Returns:
            None: saves the instance IDs in self._instance_ids instead
        """
        with self._instance_ids_lock:
            self._logger.debug(
                "Syncing valid instances for this metric from EC2")
            metrics_res = self._conn.list_metrics(metric_name=self.metric)
            self._instance_ids[:] = [
                metric.dimensions['InstanceId'][0] for metric in metrics_res]
            self._logger.debug("{} instance IDs loaded".format(
                len(self._instance_ids)))

    def process_signals(self, signals, input_id='default'):
        # Only make one request per batch of signals
        # It currently doesn't make sense to make multiple requests at once
        with self._instance_ids_lock:
            results = self._execute_requests()
        if results:
            self.notify_signals(results)

    def _execute_requests(self):
        """ Go through the saved instance IDs and capture their metrics.

        This method should be called inside of the instance IDs Lock
        """
        signals_out = []
        for instance_id in self._instance_ids:
            # Get the list of metrics
            try:
                self._logger.debug("Getting metric for {}".format(instance_id))
                metric = self._get_metric(instance_id)
                if len(metric):
                    # We only care about the last metric
                    val = metric[-1][self.statistic.name]
                    self._logger.debug("Metric's value was {}".format(val))
                    signals_out.append(Signal({
                        'instance_id': instance_id,
                        'value': val
                    }))
                else:
                    self._logger.info(
                        'Instance ID {} did not '
                        'return any metric value'.format(instance_id))
            except:
                # Unable to get the metric for this instance, ignore this
                # instance_id then
                self._logger.exception(
                    'Unable to get metric for {}'.format(instance_id))

        return signals_out

    def _get_metric(self, instance_id):
        """ Gets the value(s) of the configured metric for an instance """
        # Prepare some variables
        end_time = datetime.datetime.now()
        start_time = end_time - datetime.timedelta(minutes=self.lookback_mins)
        dimensions = {'InstanceId': [instance_id]}

        # Make the request
        results = self._conn.get_metric_statistics(
            period=(self.result_period * 60),
            start_time=start_time,
            end_time=end_time,
            metric_name=self.metric,
            namespace='AWS/EC2',
            statistics=self.statistic.name,
            dimensions=dimensions)

        return results
