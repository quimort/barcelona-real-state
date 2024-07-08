

class Property:

    def __init__(self,price,name,size,rooms,bathrooms,squere_meter_price,location,description,prop_type):
        self.price = price
        self.name = name
        self.size = size
        self.rooms = rooms
        self.bathrooms = bathrooms
        self.squere_meter_price = squere_meter_price
        self.location = location
        self.description = description
        self.prop_type = prop_type

    
    def get_price(self):
        return self.price
    
    def get_name(self):
        return self.name
    
    def get_size(self):
        return self.size
    
    def get_rooms(self):
        return self.rooms
    
    def get_bathrooms(self):
        return self.bathrooms
    
    def get_squere_meter_price(self):
        return self.squere_meter_price
    
    def get_location(self):
        return self.location
    
    def get_description(self):
        return self.description
    
    def get_prop_type(self):
        return self.prop_type