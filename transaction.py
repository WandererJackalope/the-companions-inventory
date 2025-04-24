class Transaction:
    """
    A class to represent a transaction between the player and a merchant to allow buying and selling.
    """
    def __init__(self, merch_id: int, player_id: int):
        """
        Initialize the Transaction object with merchant ID and player ID.
        :param merch_id:
        :param player_id:
        """
        self.merch_id = merch_id
        self.player_id = player_id
        self.items = []
        self.total_player_cost = 0.0 # Total cost of items player is buying
        self.total_player_revenue = 0.0 # Total revenue from items player is selling
    
    def add_item(self, item: int, user_id: int, quantity: int = 1):
        """
        Add an item to the transaction.
        :param item: item ID
        :param user_id: merchant or player ID depending on where the item is coming from.
            If the item is being bought, this is the merchant ID.
            If the item is being sold, this is the player ID.
        :param quantity: how many of the item to add to the transaction.
        :return: True if the item was added successfully, False otherwise.
        """
        return True
    
    def remove_item(self, item, user_id: int, quantity: int = 1):
        """
        Remove an item from the transaction.
        :param item: item ID
        :param user_id: merchant or player ID depending on where the item is coming from.
            If the item is being bought, this is the merchant ID.
            If the item is being sold, this is the player ID.
        :param quantity: how many of the item to add to the transaction.
        :return: True if the item was removed successfully, False otherwise.
        """
        return True
    
    def calculate_money(self):
        return True
    
    def complete_transaction(self):
        """
        Complete the transaction by updating the inventories and balance of the player and merchant.
        :return: True if the transaction was completed successfully, False otherwise.
        """
        return True
    
    