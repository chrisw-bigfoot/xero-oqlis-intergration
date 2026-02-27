"""
Financial Report Transformation Module

This module provides a single import point for transformation functions.
The actual transformation logic has been reorganized into the datasets module.
"""

# Import transformation functions from datasets module
from .datasets.balance_sheet import transform_balance_sheet
from .datasets.profit_and_loss import transform_profit_loss
from .datasets.profit_and_loss_vs_py import transform_profit_loss_ly
from .datasets.budget_summary import transform_budget_summary
from .datasets.budget_variance import transform_budget_variance

# Also provide legacy function names for backward compatibility
transform_profit_and_loss = transform_profit_loss
transform_profit_and_loss_vs_py = transform_profit_loss_ly

__all__ = [
    'transform_balance_sheet',
    'transform_budget_summary',
    'transform_budget_variance',
    'transform_profit_loss',
    'transform_profit_and_loss',  # Legacy name
    'transform_profit_loss_ly',
    'transform_profit_and_loss_vs_py',  # Legacy name
]


# All transformation logic has been moved to the datasets module.
# The imports above provide access to all transformation functions.
