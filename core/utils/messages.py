class APIMessageMixin:
    list_success_message = "All data."
    create_success_message = "Create success."
    retrieve_success_message = "Details."
    modify_success_message = "Modified successfully."
    update_success_message = "Updated successfully."
    delete_success_message = "Deleted successfully."

    def get_list_success_message(self):
        """
        Returns success message for get request list view
        """
        return self.list_success_message

    def get_create_success_message(self):
        """
        Returns success message for post request create view
        """
        return self.create_success_message

    def get_retrieve_success_message(self):
        """
        Returns success message for get request for a single object
        """
        return self.retrieve_success_message

    def get_modify_success_message(self):
        """
        Returns success message for put request
        """
        return self.modify_success_message

    def get_update_success_message(self):
        """
        Returns success message for patch request
        """
        return self.update_success_message

    def get_delete_success_message(self):
        """
        Returns success message for delete request
        """
        return self.delete_success_message
