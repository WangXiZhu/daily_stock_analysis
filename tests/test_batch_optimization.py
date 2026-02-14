
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import date, datetime, timedelta
from src.core.pipeline import StockAnalysisPipeline
from src.storage import DatabaseManager
from data_provider import DataFetcherManager
from data_provider.efinance_fetcher import EfinanceFetcher

class TestBatchOptimization(unittest.TestCase):
    def setUp(self):
        # Mock database
        self.mock_db = MagicMock(spec=DatabaseManager)
        self.mock_db.has_today_data.return_value = False
        self.mock_db.get_latest_date.return_value = None
        
        # Mock fetcher manager
        self.mock_fetcher_manager = MagicMock(spec=DataFetcherManager)
        
        # Initialize pipeline with mocks
        self.pipeline = StockAnalysisPipeline()
        self.pipeline.db = self.mock_db
        self.pipeline.fetcher_manager = self.mock_fetcher_manager
        
    def test_fetch_and_save_data_batch_efinance(self):
        """Test batch fetching logic with efinance (successful batch)"""
        stock_codes = ['600519', '000001']
        
        # Mock batch return data
        mock_df_600519 = pd.DataFrame({
            'code': ['600519'], 
            'date': [pd.Timestamp('2023-01-01')],
            'close': [100.0]
        })
        mock_df_000001 = pd.DataFrame({
            'code': ['000001'], 
            'date': [pd.Timestamp('2023-01-01')],
            'close': [10.0]
        })
        
        # Setup fetcher manager to return batch data
        self.mock_fetcher_manager.get_daily_data_batch.return_value = {
            '600519': (mock_df_600519, 'EfinanceFetcher'),
            '000001': (mock_df_000001, 'EfinanceFetcher')
        }
        
        # Execute
        results = self.pipeline.fetch_and_save_data_batch(stock_codes)
        
        # Verify fetcher was called with batch
        self.mock_fetcher_manager.get_daily_data_batch.assert_called_once()
        call_args = self.mock_fetcher_manager.get_daily_data_batch.call_args
        self.assertEqual(set(call_args[0][0]), set(stock_codes))
        
        # Verify db save was called for each stock
        self.assertEqual(self.mock_db.save_daily_data.call_count, 2)
        
        # Verify results
        self.assertTrue(results['600519'])
        self.assertTrue(results['000001'])

    def test_fetch_and_save_data_batch_incremental(self):
        """Test incremental update logic (calculating days)"""
        stock_codes = ['600519']
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # Setup DB to return yesterday as latest date
        self.mock_db.get_latest_date.return_value = yesterday
        
        # Setup fetcher mock
        self.mock_fetcher_manager.get_daily_data_batch.return_value = {}
        
        # Execute
        self.pipeline.fetch_and_save_data_batch(stock_codes)
        
        # Verify fetch days calculation
        # days_diff = 1, so fetch_days should be 1 + 5 = 6
        call_args = self.mock_fetcher_manager.get_daily_data_batch.call_args
        self.assertEqual(call_args[1]['days'], 6)

    def test_analyze_stocks_batch(self):
        """Test StockAnalysisEngine.analyze_stocks_batch"""
        # Mock analysis engine components
        self.pipeline.analysis_engine.analyzer = MagicMock()
        self.pipeline.analysis_engine.analyzer.analyze_batch_optimized.return_value = {
            '600519': MagicMock(code='600519', sentiment_score=80)
        }
        
        # Configure fetcher manager mock
        mock_fetcher = MagicMock()
        mock_quote = MagicMock()
        mock_quote.name = "茅台"
        mock_quote.price = 100.0
        mock_quote.volume_ratio = 1.0 # Float required
        mock_fetcher.get_realtime_quote.return_value = mock_quote
        mock_fetcher.get_chip_distribution.return_value = None
        self.pipeline.analysis_engine.fetcher_manager = mock_fetcher
        
        self.pipeline.analysis_engine.db = MagicMock()
        self.pipeline.analysis_engine.db.get_analysis_context.return_value = {} # Empty context
        self.pipeline.analysis_engine.search_service = MagicMock()
        self.pipeline.analysis_engine.search_service.is_available = False
        
        # Execute
        results = self.pipeline.analysis_engine.analyze_stocks_batch(['600519'])
        
        # Verify
        self.pipeline.analysis_engine.analyzer.analyze_batch_optimized.assert_called_once()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].code, '600519')

    def test_pipeline_run_batches(self):
        """Test that pipeline.run correctly batches tasks"""
        self.pipeline.config.batch_size = 2
        stock_codes = ['1', '2', '3', '4', '5']
        
        # Mock process_batch to avoid actual execution
        self.pipeline.process_batch = MagicMock(return_value=[])
        self.pipeline.fetch_and_save_data_batch = MagicMock(return_value={})
        self.pipeline.fetcher_manager.prefetch_realtime_quotes.return_value = 0 # Return int
        
        # Run
        self.pipeline.run(stock_codes, dry_run=False, send_notification=False)
        
        # Verify process_batch call count
        # 5 stocks, batch size 2 -> [1,2], [3,4], [5] -> 3 batches
        self.assertEqual(self.pipeline.process_batch.call_count, 3)
        
        # Verify call args
        calls = self.pipeline.process_batch.call_args_list
        # Note: Depending on thread execution order, calls might be permuted, 
        # but the arguments should match the batches.
        # However, list equality checks order of batch contents, which is deterministic (slicing).
        # But `calls` order depends on execution if run is async? No, submission is synchronous.
        # Wait, run() uses ThreadPoolExecutor.submit.
        # The submissions happen in order of iteration.
        self.assertEqual(calls[0][0][0], ['1', '2'])
        self.assertEqual(calls[1][0][0], ['3', '4'])
        self.assertEqual(calls[2][0][0], ['5'])

if __name__ == '__main__':
    unittest.main()
