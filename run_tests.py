#!/usr/bin/env python3
"""
測試運行腳本

提供多種測試運行選項
"""
import sys
import unittest
import argparse
import os


def setup_test_environment():
    """設置測試環境"""
    # 確保當前目錄在 Python 路徑中
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)


def run_unit_tests():
    """運行單元測試"""
    print("🧪 運行單元測試...")
    loader = unittest.TestLoader()
    
    try:
        from test_fubon_account_new import TestFubonAccountUnit, TestFubonAccountErrorHandling
        
        suite = unittest.TestSuite()
        suite.addTests(loader.loadTestsFromTestCase(TestFubonAccountUnit))
        suite.addTests(loader.loadTestsFromTestCase(TestFubonAccountErrorHandling))
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        return result.wasSuccessful()
        
    except ImportError as e:
        print(f"❌ 無法導入單元測試模組: {e}")
        return False


def run_integration_tests():
    """運行集成測試"""
    print("🔗 運行集成測試...")
    
    # 檢查環境變數
    required_vars = [
        'FUBON_NATIONAL_ID',
        'FUBON_ACCOUNT_PASS', 
        'FUBON_CERT_PATH'
    ]
    
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    if missing_vars:
        print(f"❌ 缺少環境變數: {missing_vars}")
        print("請設置必要的環境變數後再運行集成測試")
        return False
    
    loader = unittest.TestLoader()
    
    try:
        from test_fubon_account_new import TestFubonAccountIntegration
        from test_fubon_account import TestFubonAccount
        
        suite = unittest.TestSuite()
        suite.addTests(loader.loadTestsFromTestCase(TestFubonAccountIntegration))
        suite.addTests(loader.loadTestsFromTestCase(TestFubonAccount))
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        return result.wasSuccessful()
        
    except ImportError as e:
        print(f"❌ 無法導入集成測試模組: {e}")
        return False


def run_performance_tests():
    """運行性能測試"""
    print("⚡ 運行性能測試...")
    
    loader = unittest.TestLoader()
    
    try:
        from test_fubon_account_new import TestFubonAccountPerformance
        
        suite = loader.loadTestsFromTestCase(TestFubonAccountPerformance)
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        return result.wasSuccessful()
        
    except ImportError as e:
        print(f"❌ 無法導入性能測試模組: {e}")
        return False


def run_all_tests():
    """運行所有測試"""
    print("🚀 運行所有測試...")
    
    success = True
    
    # 運行單元測試
    if not run_unit_tests():
        success = False
        print("❌ 單元測試失敗")
    else:
        print("✅ 單元測試通過")
    
    print("\n" + "="*50 + "\n")
    
    # 運行集成測試
    if not run_integration_tests():
        success = False
        print("❌ 集成測試失敗")
    else:
        print("✅ 集成測試通過")
    
    print("\n" + "="*50 + "\n")
    
    # 運行性能測試
    if not run_performance_tests():
        success = False
        print("❌ 性能測試失敗")
    else:
        print("✅ 性能測試通過")
    
    return success


def run_specific_test(test_name):
    """運行特定測試"""
    print(f"🎯 運行特定測試: {test_name}")
    
    loader = unittest.TestLoader()
    
    try:
        # 嘗試從不同模組載入測試
        modules_to_try = [
            'test_fubon_account_new',
            'test_fubon_account'
        ]
        
        for module_name in modules_to_try:
            try:
                module = __import__(module_name)
                suite = loader.loadTestsFromName(test_name, module)
                
                runner = unittest.TextTestRunner(verbosity=2)
                result = runner.run(suite)
                
                return result.wasSuccessful()
                
            except (ImportError, AttributeError):
                continue
        
        print(f"❌ 找不到測試: {test_name}")
        return False
        
    except Exception as e:
        print(f"❌ 運行測試時發生錯誤: {e}")
        return False


def list_available_tests():
    """列出可用的測試"""
    print("📋 可用的測試:")
    print("\n🧪 單元測試:")
    print("  - TestFubonAccountUnit")
    print("  - TestFubonAccountErrorHandling")
    
    print("\n🔗 集成測試:")
    print("  - TestFubonAccountIntegration")
    print("  - TestFubonAccount")
    
    print("\n⚡ 性能測試:")
    print("  - TestFubonAccountPerformance")
    
    print("\n💡 使用範例:")
    print("  python run_tests.py --unit")
    print("  python run_tests.py --integration")
    print("  python run_tests.py --performance")
    print("  python run_tests.py --all")
    print("  python run_tests.py --test TestFubonAccountUnit.test_extract_price_data_from_dict")


def main():
    """主函數"""
    setup_test_environment()
    
    parser = argparse.ArgumentParser(description='FubonAccount 測試運行器')
    parser.add_argument('--unit', action='store_true', help='運行單元測試')
    parser.add_argument('--integration', action='store_true', help='運行集成測試')
    parser.add_argument('--performance', action='store_true', help='運行性能測試')
    parser.add_argument('--all', action='store_true', help='運行所有測試')
    parser.add_argument('--test', type=str, help='運行特定測試')
    parser.add_argument('--list', action='store_true', help='列出可用測試')
    
    args = parser.parse_args()
    
    if args.list:
        list_available_tests()
        return
    
    success = True
    
    if args.unit:
        success = run_unit_tests()
    elif args.integration:
        success = run_integration_tests()
    elif args.performance:
        success = run_performance_tests()
    elif args.all:
        success = run_all_tests()
    elif args.test:
        success = run_specific_test(args.test)
    else:
        print("請指定要運行的測試類型。使用 --help 查看選項。")
        list_available_tests()
        return
    
    if success:
        print("\n🎉 所有測試都通過了！")
        sys.exit(0)
    else:
        print("\n💥 有測試失敗了！")
        sys.exit(1)


if __name__ == "__main__":
    main()