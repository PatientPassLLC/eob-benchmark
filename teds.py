"""
TEDS (Tree Edit Distance based Similarity) for table structure evaluation.

Based on the ICDAR 2019 paper:
"ICDAR 2019 Competition on Table Detection and Recognition (cTDaR)"
"""

from bs4 import BeautifulSoup
from apted import APTED, Config
from apted.helpers import Tree


class TableNode:
    """Represents a node in the table tree structure."""

    def __init__(self, tag, colspan=None, rowspan=None, content=None):
        self.tag = tag
        self.colspan = colspan
        self.rowspan = rowspan
        self.content = content
        self.children = []

    def __repr__(self):
        if self.tag == 'td' or self.tag == 'th':
            return f"{self.tag}:{self.content}"
        return self.tag


class TableTree(Tree):
    """Adapter for APTED tree operations."""

    def __init__(self, node):
        self.node = node
        self.children = [TableTree(child) for child in node.children]


class TableConfig(Config):
    """APTED configuration for table comparison."""

    def __init__(self, structure_only=False):
        self.structure_only = structure_only

    def rename(self, node1, node2):
        """Cost of renaming node1 to node2."""
        if node1.node.tag != node2.node.tag:
            return 1

        if not self.structure_only:
            # Compare content for td/th cells
            if node1.node.tag in ['td', 'th']:
                if node1.node.content != node2.node.content:
                    return 1

        # Compare structure attributes
        if node1.node.colspan != node2.node.colspan:
            return 1
        if node1.node.rowspan != node2.node.rowspan:
            return 1

        return 0

    def delete(self, node):
        """Cost of deleting a node."""
        return 1

    def insert(self, node):
        """Cost of inserting a node."""
        return 1


def html_table_to_tree(table_html):
    """Convert HTML table string to tree structure."""
    soup = BeautifulSoup(table_html, 'html.parser')
    table = soup.find('table')

    if not table:
        raise ValueError("No <table> found in HTML")

    def build_tree(element):
        node = TableNode(element.name)

        # Extract attributes
        if element.name in ['td', 'th']:
            node.content = element.get_text(strip=True)
            node.colspan = element.get('colspan')
            node.rowspan = element.get('rowspan')

        # Build children
        for child in element.children:
            if hasattr(child, 'name') and child.name in ['tr', 'th', 'td', 'thead', 'tbody', 'tfoot']:
                node.children.append(build_tree(child))

        return node

    return build_tree(table)


class TEDS:
    """
    Table Edit Distance based Similarity metric.

    Args:
        structure_only: If True, only compare table structure (ignore cell content)
    """

    def __init__(self, structure_only=False):
        self.structure_only = structure_only

    def evaluate(self, pred_html, gt_html):
        """
        Calculate TEDS score between predicted and ground truth tables.

        Args:
            pred_html: Predicted table HTML string
            gt_html: Ground truth table HTML string

        Returns:
            float: TEDS score between 0 and 1 (1 = perfect match)
        """
        try:
            pred_tree = html_table_to_tree(pred_html)
            gt_tree = html_table_to_tree(gt_html)
        except Exception as e:
            print(f"Warning: Failed to parse table HTML: {e}")
            return 0.0

        pred_tree_obj = TableTree(pred_tree)
        gt_tree_obj = TableTree(gt_tree)

        config = TableConfig(structure_only=self.structure_only)
        apted = APTED(pred_tree_obj, gt_tree_obj, config)

        # Calculate edit distance
        edit_distance = apted.compute_edit_distance()

        # Normalize by the size of the larger tree
        max_size = max(self._tree_size(pred_tree), self._tree_size(gt_tree))

        if max_size == 0:
            return 1.0

        # Convert distance to similarity (1 - normalized_distance)
        teds_score = 1.0 - (edit_distance / max_size)

        return max(0.0, min(1.0, teds_score))

    def _tree_size(self, node):
        """Count total nodes in tree."""
        size = 1
        for child in node.children:
            size += self._tree_size(child)
        return size


if __name__ == "__main__":
    # Test
    teds = TEDS(structure_only=False)

    table1 = """<table>
    <tr><th>A</th><th>B</th></tr>
    <tr><td>1</td><td>2</td></tr>
    </table>"""

    table2 = """<table>
    <tr><th>A</th><th>B</th></tr>
    <tr><td>1</td><td>2</td></tr>
    </table>"""

    score = teds.evaluate(table1, table2)
    print(f"TEDS Score: {score}")  # Should be 1.0
