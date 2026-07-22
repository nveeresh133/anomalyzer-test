from datetime import datetime

class BranchManager:

    @staticmethod
    def generate_branch_name(resource: str, recommendation: str):

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        return f"feature/{resource}-{recommendation}-{timestamp}"