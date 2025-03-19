all = {
    "pages": {
        "home": {  # API key: pages_home  GET values key=pages_home
            "title": {
                "ar": "الرئيسية",
                "en": "home"
            },
            # //{atom name}_{section}_{index}
            "sections": [
                {
                    "key": "hero_home_1",
                    #-- the key is mandatory
                    "type": "hero",
                    "title": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "description": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "image": {
                        "ar":"url",
                        "en":"url"
                    }
                },
                {
                    "key": "two_columns_home_1",
                    #-- the key is mandatory
                    "type": "two_columns",
                    "title": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "description": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "columns_Section": [
                         #--first column
                         {
                             "key": "first_column",#-- the key is mandatory
                             "title": {
                                 "ar": "عربي",
                                 "en": "Our Vision"
                             },
                             "description": {
                                 "ar": "عربي",
                                 "en": "Our Vision description"
                             },
                             "content_alignment": "start",
                             #-- 'start'|'end',
                             "icon": "checkmark",
                             #--#-- other icon names might be set here
                         },
                         #--second column
                         {
                             "key": "second_column",#-- the key is mandatory
                             "title": {
                                 "ar": "عربي",
                                 "en": "Our mission"
                             },
                             "description": {
                                 "ar": "عربي",
                                 "en": "Our mission description"
                             },
                             "content_alignment": "start",
                             #-- 'start'|'end',
                             "icon": "checkmark",
                             #--#-- other icon names might be set here
                         }
                    ],
                },
                {
                    "key": "featured_courses_home_1",
                    "type": "featured_courses",
                    "title": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "description": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "grid_type": "9" #-- accept 3 | 6 | 9 | all
                },
                {
                    "key": "static_metrics_section_home_1",
                    "type": "static_metrics_section",
                    "title": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "description": {
                        "ar": "المعهد العقاري",
                        "en": "SREI excellence"
                    },
                    "alignment": "center",
                    #-- start | end | center
                    "list_of_static_metrics": [
                        {
                            "key": "metric_1",
                            "title": {
                                "ar": "4 ملايين",
                                "en": "4M+"
                            },
                            "description": {
                                "ar": "4 ملايين",
                                "en": "4M+"
                            },
                        },
                        {
                            "key": "metric_2",
                            "title": {
                                "ar": "4 ملايين",
                                "en": "4M+"
                            },
                            "description": {
                                "ar": "4 ملايين",
                                "en": "4M+"
                            },
                        },
                        {
                            "key": "metric_3",
                            "title": {
                                "ar": "4 ملايين",
                                "en": "4M+"
                            },
                            "description": {
                                "ar": "4 ملايين",
                                "en": "4M+"
                            },
                        }
                    ]
                },
                {
                    "key": "live_metrics_section_home_1",
                    "type": "live_metrics_section",
                    "options": [
                        {
                            "key": "courses",
                            "is_checked": True,
                            #-- the value is boolen
                            "title": {
                                "ar": "المعهد العقاري",
                                "en": "SREI excellence"
                            },
                            "description": {
                                "ar": "المعهد العقاري",
                                "en": "SREI excellence"
                            },
                        },
                        {
                            "key": "learners",
                            "is_checked": True,
                            #-- the value is boolen
                            "title": {
                                "ar": "المعهد العقاري",
                                "en": "SREI excellence"
                            },
                            "description": {
                                "ar": "المعهد العقاري",
                                "en": "SREI excellence"
                            },
                        },
                        {
                            "key": "instructors",
                            "is_checked": True,
                            #-- the value is boolen
                            "title": {
                                "ar": "المعهد العقاري",
                                "en": "SREI excellence"
                            },
                            "description": {
                                "ar": "المعهد العقاري",
                                "en": "SREI excellence"
                            },
                        }
                    ]
                },
            ]
        },
        "courses": {
            #--#--  API key: pages_courses
        },
        "about_us": {
            #--#--  API key: pages_about_us
        },
        "terms": {
            #--#--  API key: pages_terms
        },
        "contact_us": {
            #--#--  API key: pages_contact_us
        },
        "pages_custom_page_1": {
            #--#--  API key: pages_custom_page_1
            "title": {
                "ar": "المعهد العقاري",
                "en": "SREI excellence"
            }, # .... the rest of the properties
            #--#-- other details similar to home
        },
        "pages_custom_page_2": {
            #--#--  API key: pages_custom_page_2
            "title": {
                "ar": "عربي2",
                "en": "something2"
            }, # .... the rest of the properties
        },
        "pages_custom_page_3": {  #--  API key: pages_custom_page_3
            "title": {
                "ar": "عربي3",
                "en": "something3"
            }, # .... the rest of the properties
        },

        "pages_custom_page_4": {},  #--  API key: pages_custom_page_4

        "pages_custom_page_5": {},  #--  API key: pages_custom_page_5

        "pages_custom_page_6": {},   #--  API key: pages_custom_page_6
        # ....... to pages_custom_page_50
    },

    "custom_pages": [  #--#--  API key: custom_pages
        "pages_custom_page_1",
        "pages_custom_page_2",
        "pages_custom_page_5"
    ],


    "visual_identity": {
        "colors": {
            "primary_color: "#00ff00",  #--  API key: colors_primary_color
            "secondery_color: "#00ff00",  #--  API key: colors_secondery_color
        },
        "fonts": {
            "headind": {  #--  API key: fonts_heading
                "ar":"",
                "en":""
            },
            "text": {  #--  API key: fonts_text
                "ar":"",
                "en":""
            }
        }
    },

    "platform_settings": {  #--  API key: platform_settings
        "site_name": {
            "ar": "المعهد العقاري",
            "en": "SREI excellence"
        },
        "subtitle": {
            "ar": "المعهد العقاري",
            "en": "SREI excellence"
        },
        "favicon": ' url',
        "thumbnail": ' url',
        "social_media_image": ' url',
        "meta_description": {
            "ar": "المعهد العقاري",
            "en": "SREI excellence"
        },
    },

    "footer": {
        "sections": [  #--  API key: footer_sections
             {
                 "key": "option_1",
                 "link_title": {
                     "ar": "",
                     "en": ""
                 },
                 "page": "courses",  # or home, about_us, pages_custom_page_1, ... or https://
                 #-- Display one of the list of pages,
                 "new_tab": True,
             },
             {
                 "key": "option_2",
                 "link_title": {
                     "ar": "",
                     "en": ""
                 },
                 "page": "about_us",  # or home, about_us, pages_custom_page_1, ... or https://
                 #-- Display one of the list of pages,
                 "new_tab": True,
             },
             {
                 "key": "option_3",
                 "link_title": {
                     "ar": "",
                     "en": ""
                 },
                 "page": "pages_custom_page_1",  # or home, about_us, pages_custom_page_1, ... or https://
                 #-- Display one of the list of pages,
                 "new_tab": True,
             },
        ],
        "social_media_links": [  #--  API key: footer_social_media_links
            {
                "provider": "facebook",
                "value": "url"
            },
            {
                "provider": "x",
                "value": "url"
            }
        ]
    },

    "header": {
        "sections": [  #--  API key: header_sections
            {
                "key": "option_1",
                "link_title": {
                    "ar": "",
                    "en": ""
                },
                "page": "courses",  # or home, about_us, pages_custom_page_1, ... or https://
                #-- Display one of the list of pages,
                "new_tab": True,
            },
            {
                "key": "option_2",
                "link_title": {
                    "ar": "",
                    "en": ""
                },
                "page": "about_us",  # or home, about_us, pages_custom_page_1, ... or https://
                #-- Display one of the list of pages,
                "new_tab": True,
            },
            {
                "key": "option_3",
                "link_title": {
                    "ar": "",
                    "en": ""
                },
                "page": "pages_custom_page_1",  # or home, about_us, pages_custom_page_1, ... or https://
                #-- Display one of the list of pages,
                "new_tab": True,
            },
        ],
        "logo": {  #--  API key: header_logo
            "ar": "url",
            "en": "url"
        },
        "combined_login": True,  #--  API key: header_combined_login
    },
}
