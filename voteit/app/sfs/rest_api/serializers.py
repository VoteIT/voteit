from rest_framework import serializers


class VoterWeightSerializer(serializers.Serializer):
    user = serializers.IntegerField()
    weight = serializers.IntegerField()


class SetDelegationVotersSerializer(serializers.Serializer):
    weights = serializers.ListField(child=VoterWeightSerializer(), default=list)

    def validate_weights(self, value):
        found = set()
        for vw in value:
            if vw["user"] in found:
                raise serializers.ValidationError(f"Duplicate user entry: {vw['user']}")
            found.add(vw["user"])
        return value
