#curl --request GET \
#  --url curl --request GET \
#  --url 'https://api.cal.com/v1/slots?apiKey=cal_live_77eacdcac0f030304bc34c230e10dba2&startTime=2025-06-11&endTime=2025-06-12&timeZone=PST'

# this works
curl --request GET      --url 'https://api.cal.com/v2/bookings?attendeeEmail=justinwu2020@gmail.com'     \
    --header 'Authorization: Bearer cal_live_77eacdcac0f030304bc34c230e10dba2' \    
    --header 'Content-Type: application/json' | json_pp | more
