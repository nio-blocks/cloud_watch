from unittest.mock import patch
from boto.exception import BotoServerError
from boto.ec2.cloudwatch import CloudWatchConnection
from nio.block.terminals import DEFAULT_TERMINAL
from nio.signal.base import Signal
from nio.testing.block_test_case import NIOBlockTestCase
from ..cloud_watch_block import CloudWatch


class SampleMetric():

    """ A class to create a "Metric-like" object """

    def __init__(self, instance_id):
        """ Create a sample metric for an EC2 instance """
        self.dimensions = {'InstanceId': [instance_id]}
        self.namespace = 'AWS/EC2'
        self.name = 'MyMetricName'


@patch('boto.ec2.cloudwatch.CloudWatchConnection.get_metric_statistics')
@patch('boto.ec2.cloudwatch.CloudWatchConnection.list_metrics')
@patch(CloudWatch.__module__ + '.connect_to_region')
class TestCloudWatch(NIOBlockTestCase):

    def test_connect(self, connect_func, list_func, stats_func):
        """ Make sure we connect with the right creds """
        blk = CloudWatch()
        self.configure_block(blk, {
            'creds': {
                'region': 'us_east_1',
                'access_key': 'FAKEKEY',
                'access_secret': 'FAKESECRET'
            }
        })
        connect_func.assert_called_once_with(
            'us-east-1',
            aws_access_key_id='FAKEKEY',
            aws_secret_access_key='FAKESECRET')

    def test_sync_metrics(self, connect_func, list_func, stats_func):
        """ Make sure we properly load metrics """
        blk = CloudWatch()
        connect_func.return_value = CloudWatchConnection('key', 'secret')
        # We're going to simulate the result returned two instances
        list_func.return_value = [
            SampleMetric('instance-1'),
            SampleMetric('instance-2')]

        self.configure_block(blk, {
            'metric': 'MyMetricName'
        })

        # Make sure the list metrics call had the right metric name
        # and that the metrics got saved properly
        list_func.assert_called_once_with(metric_name='MyMetricName')
        self.assertEqual(len(blk._metrics), 2)

    def test_get_metrics(self, connect_func, list_func, stats_func):
        """ Make sure we make a proper get_metric_statistics call """
        blk = CloudWatch()
        connect_func.return_value = CloudWatchConnection('key', 'secret')
        blk._metrics = [SampleMetric('instance-1')]
        self.configure_block(blk, {
            'metric': 'MyMetricName',
            'lookback_mins': 60,  # 1 hour
            'result_period': 5,  # 5 mins
            'statistic': 'Maximum'
        })

        stats_func.return_value = [{'Maximum': 2}]

        # Send two signals into the block
        # This should only trigger one request per metric
        blk.process_signals([Signal(), Signal()])
        stats_func.assertCalledOnceWith(
            period=300,  # 5 mins...in seconds
            metric_name='MyMetricName',
            namespace='AWS/EC2',  # Make sure it uses the metric's namespace
            statistics='Maximum',
            dimensions={'InstanceId': ['instance-1']})

    def test_metric_results(self, connect_func, list_func, stats_func):
        """ Make sure we properly handle the results from get statistics """
        blk = CloudWatch()
        connect_func.return_value = CloudWatchConnection('key', 'secret')
        self.configure_block(blk, {
            'metric': 'MyMetricName',
            'lookback_mins': 60,  # 1 hour
            'result_period': 5,  # 5 mins
            'statistic': 'Maximum'
        })

        # 4 metrics will run, one gets multiple results, one gets one result,
        # one gets no results, and one throws an error
        blk._metrics = [
            SampleMetric('instance-{}'.format(i)) for i in range(4)]
        stats_func.side_effect = [
            [{
                'Average': 1.5,
                'Maximum': 2,
                'Minimum': 1
            }, {
                'Average': 2.5,
                'Maximum': 3,
                'Minimum': 2
            }],
            [{
                'Average': 3.5,
                'Maximum': 5,
                'Minimum': 2
            }],
            [],
            Exception
        ]

        # Send two signals into the block
        # This should only trigger one request per metric
        blk.process_signals([Signal(), Signal()])

        # Only 2 should be notified - empty and error are ignored
        self.assert_num_signals_notified(2)

        # Make sure we grabbed the maximum as the value and not the others
        # We also want to make sure we only used the first value of the results
        self.assertEqual(self.last_notified[DEFAULT_TERMINAL][0].value, 2)
        self.assertEqual(
            self.last_notified[DEFAULT_TERMINAL][0].dimensions['InstanceId'],
            ['instance-0'])
        self.assertEqual(self.last_notified[DEFAULT_TERMINAL][1].value, 5)
        self.assertEqual(
            self.last_notified[DEFAULT_TERMINAL][1].dimensions['InstanceId'],
            ['instance-1'])

    def test_error_connecting(self, connect_func, list_func, stats_func):
        """ Make sure connection errors are handled properly """
        connect_func.return_value = CloudWatchConnection('key', 'secret')
        list_func.side_effect = BotoServerError(500, 'Fake Error connecting')
        blk = CloudWatch()

        # Make sure we still raise the exception when we configure
        with self.assertRaises(BotoServerError):
            self.configure_block(blk, {})
