import yaml


class YamlEditor:

    @staticmethod
    def update_field(content: str, field: str, value):

        data = yaml.safe_load(content)

        data["spec"][field] = value

        return yaml.dump(data, sort_keys=False)